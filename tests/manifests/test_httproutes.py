# Copyright 2026 Element Creations Ltd
#
# SPDX-License-Identifier: AGPL-3.0-only


import pytest

from . import (
    DeployableDetails,
    PropertyType,
    all_deployables_details,
    services_values_files_to_test,
    values_files_to_test,
)
from .utils import iterate_deployables_ingress_parts, template_to_deployable_details


def configure_routes(values):
    """Switch the chart to HTTPRoute and reuse each component's Ingress host."""
    values["inboundTrafficHandler"] = "routes"

    def copy_host(deployable_details: DeployableDetails):
        if deployable_details.name == "well-known":
            return
        ingress_values = deployable_details.get_helm_values(values, PropertyType.Ingress) or {}
        host = ingress_values.get("host")
        if host:
            deployable_details.set_helm_values(values, PropertyType.Routes, {"host": host})

    iterate_deployables_ingress_parts(copy_host)


def expected_route_hosts(values) -> list[str]:
    hosts = []
    for deployable_details in all_deployables_details:
        if not deployable_details.has_ingress:
            continue
        if not deployable_details.get_helm_values(values, PropertyType.Enabled, default_value=False):
            continue
        # The well-known HTTPRoute is rendered with serverName, not routes.host.
        if deployable_details.name == "well-known":
            hosts.append(values["serverName"])
            continue
        routes_values = deployable_details.get_helm_values(values, PropertyType.Routes) or {}
        if routes_values.get("host"):
            hosts.append(routes_values["host"])
    return hosts


def component_is_redirect(template) -> bool:
    rules = template["spec"].get("rules") or []
    return bool(rules and any(item.get("type") == "RequestRedirect" for item in rules[0].get("filters") or []))


def component_httproutes(templates):
    for template in templates:
        if template["kind"] != "HTTPRoute" or component_is_redirect(template):
            continue
        yield template


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_has_httproute(values, make_templates):
    configure_routes(values)
    for template in component_httproutes(await make_templates(values)):
        assert template_to_deployable_details(template).has_ingress


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_httproute_is_expected_host(values, make_templates):
    configure_routes(values)
    expected_hosts = expected_route_hosts(values)

    found_hosts = []
    for template in component_httproutes(await make_templates(values)):
        assert "hostnames" in template["spec"]
        assert len(template["spec"]["hostnames"]) == 1
        found_hosts.append(template["spec"]["hostnames"][0])
    # One HTTPRoute per component, so a shared hostname still has to appear once per route.
    assert sorted(found_hosts) == sorted(expected_hosts)


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_httproute_paths_are_path_prefix(values, make_templates):
    configure_routes(values)
    for template in component_httproutes(await make_templates(values)):
        assert "rules" in template["spec"]
        assert len(template["spec"]["rules"]) > 0
        for rule in template["spec"]["rules"]:
            assert "matches" in rule
            for match in rule["matches"]:
                assert match["path"]["type"] == "PathPrefix"


@pytest.mark.parametrize("values_file", values_files_to_test - services_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_annotations_by_default(values, make_templates):
    configure_routes(values)
    for template in component_httproutes(await make_templates(values)):
        assert "annotations" not in template["metadata"]


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_renders_component_httproute_annotations(values, make_templates):
    configure_routes(values)

    def set_annotations(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.Routes,
            {"annotations": {"component": "set"}},
        )

    iterate_deployables_ingress_parts(set_annotations)

    for template in component_httproutes(await make_templates(values)):
        assert template["metadata"]["annotations"]["component"] == "set"


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_renders_global_httproute_annotations(values, make_templates):
    configure_routes(values)
    values.setdefault("routes", {})["annotations"] = {"global": "set"}

    for template in component_httproutes(await make_templates(values)):
        assert template["metadata"]["annotations"]["global"] == "set"


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_merges_global_and_component_httproute_annotations(values, make_templates):
    configure_routes(values)

    def set_annotations(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.Routes,
            {
                "annotations": {
                    "component": "set",
                    "merged": "from_component",
                    "global": None,
                }
            },
        )

    iterate_deployables_ingress_parts(set_annotations)
    values.setdefault("routes", {})["annotations"] = {
        "global": "set",
        "merged": "from_global",
    }

    for template in component_httproutes(await make_templates(values)):
        annotations = template["metadata"]["annotations"]
        assert annotations["component"] == "set"
        assert annotations["merged"] == "from_component"
        # A null annotation removes the global key from the HTTPRoute.
        assert "global" not in annotations


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_parent_refs_by_default(values, make_templates):
    configure_routes(values)
    for template in component_httproutes(await make_templates(values)):
        assert "parentRefs" not in template["spec"]


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_uses_component_existing_gateways(values, make_templates):
    configure_routes(values)

    def set_parent_refs(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.Routes,
            {"existingGateways": [{"name": "component", "sectionName": "https"}]},
        )

    iterate_deployables_ingress_parts(set_parent_refs)

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "component", "sectionName": "https"}]


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_uses_global_existing_gateways(values, make_templates):
    configure_routes(values)
    values.setdefault("routes", {})["existingGateways"] = [{"name": "global", "namespace": "gateway-ns"}]

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "global", "namespace": "gateway-ns"}]


@pytest.mark.parametrize("values_file", values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_existing_gateways_beats_global(values, make_templates):
    configure_routes(values)

    def set_parent_refs(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.Routes,
            {"existingGateways": [{"name": "component"}]},
        )

    iterate_deployables_ingress_parts(set_parent_refs)
    values.setdefault("routes", {})["existingGateways"] = [{"name": "global"}]

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "component"}]


@pytest.mark.parametrize("values_file", values_files_to_test - services_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_when_handler_is_none(values, make_templates):
    configure_routes(values)
    values["inboundTrafficHandler"] = "none"
    assert list(component_httproutes(await make_templates(values))) == []


@pytest.mark.parametrize("values_file", values_files_to_test - services_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_handler_none_beats_global_routes(values, make_templates):
    configure_routes(values)

    def set_handler_none(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(values, PropertyType.InboundTrafficHandler, "none")

    iterate_deployables_ingress_parts(set_handler_none)
    assert list(component_httproutes(await make_templates(values))) == []

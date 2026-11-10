# Copyright 2026 Element Creations Ltd
#
# SPDX-License-Identifier: AGPL-3.0-only


import pytest

from . import (
    DeployableDetails,
    PropertyType,
    all_deployables_details,
    gatewayapi_values_files_to_test,
)
from .utils import iterate_deployables_ingress_parts, template_to_deployable_details


def expected_route_hosts(values) -> list[str]:
    hosts = []
    for deployable_details in all_deployables_details:
        if not deployable_details.has_ingress:
            continue
        if not deployable_details.get_helm_values(values, PropertyType.Enabled, default_value=False):
            continue
        # The well-known HTTPRoute is rendered with serverName, not the component host.
        if deployable_details.name == "well-known":
            hosts.append(values["serverName"])
            continue
        host = deployable_details.get_helm_values(values, PropertyType.Host, default_value="")
        if host:
            hosts.append(host)
    return hosts


def component_is_redirect(template) -> bool:
    rules = template["spec"].get("rules") or []
    return bool(rules and any(item.get("type") == "RequestRedirect" for item in rules[0].get("filters") or []))


def traffic_policies(templates, kind: str):
    return [template for template in templates if template["kind"] == kind]


def component_httproutes(templates):
    for template in templates:
        if template["kind"] != "HTTPRoute" or component_is_redirect(template):
            continue
        yield template


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_has_httproute(values, make_templates):
    for template in component_httproutes(await make_templates(values)):
        assert template_to_deployable_details(template).has_ingress


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_httproute_is_expected_host(values, make_templates):
    expected_hosts = expected_route_hosts(values)

    found_hosts = []
    for template in component_httproutes(await make_templates(values)):
        assert "hostnames" in template["spec"]
        assert len(template["spec"]["hostnames"]) == 1
        found_hosts.append(template["spec"]["hostnames"][0])
    # One HTTPRoute per component, so a shared hostname still has to appear once per route.
    assert sorted(found_hosts) == sorted(expected_hosts)


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_httproute_paths_are_path_prefix(values, make_templates):
    for template in component_httproutes(await make_templates(values)):
        assert "rules" in template["spec"]
        assert len(template["spec"]["rules"]) > 0
        for rule in template["spec"]["rules"]:
            assert "matches" in rule
            for match in rule["matches"]:
                assert match["path"]["type"] == "PathPrefix"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_annotations_by_default(values, make_templates):
    for template in component_httproutes(await make_templates(values)):
        assert "annotations" not in template["metadata"]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_renders_component_httproute_annotations(values, make_templates):
    def set_annotations(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.HttpRoutes,
            {"annotations": {"component": "set"}},
        )

    iterate_deployables_ingress_parts(set_annotations)

    for template in component_httproutes(await make_templates(values)):
        assert template["metadata"]["annotations"]["component"] == "set"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_renders_global_httproute_annotations(values, make_templates):
    values.setdefault("httpRoutes", {})["annotations"] = {"global": "set"}

    for template in component_httproutes(await make_templates(values)):
        assert template["metadata"]["annotations"]["global"] == "set"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_merges_global_and_component_httproute_annotations(values, make_templates):
    def set_annotations(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.HttpRoutes,
            {
                "annotations": {
                    "component": "set",
                    "merged": "from_component",
                    "global": None,
                }
            },
        )

    iterate_deployables_ingress_parts(set_annotations)
    values.setdefault("httpRoutes", {})["annotations"] = {
        "global": "set",
        "merged": "from_global",
    }

    for template in component_httproutes(await make_templates(values)):
        annotations = template["metadata"]["annotations"]
        assert annotations["component"] == "set"
        assert annotations["merged"] == "from_component"
        # A null annotation removes the global key from the HTTPRoute.
        assert "global" not in annotations


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_parent_refs_by_default(values, make_templates):
    for template in component_httproutes(await make_templates(values)):
        assert "parentRefs" not in template["spec"]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_uses_component_http_route_parent_refs(values, make_templates):
    def set_parent_refs(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.HttpRoutes,
            {"parentReferences": [{"name": "component", "sectionName": "https"}]},
        )

    iterate_deployables_ingress_parts(set_parent_refs)

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "component", "sectionName": "https"}]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_uses_global_http_route_parent_refs(values, make_templates):
    values.setdefault("httpRoutes", {})["parentReferences"] = [{"name": "global", "namespace": "gateway-ns"}]

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "global", "namespace": "gateway-ns"}]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_http_route_parent_refs_beats_global(values, make_templates):
    def set_parent_refs(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.HttpRoutes,
            {"parentReferences": [{"name": "component"}]},
        )

    iterate_deployables_ingress_parts(set_parent_refs)
    values.setdefault("httpRoutes", {})["parentReferences"] = [{"name": "global"}]

    for template in component_httproutes(await make_templates(values)):
        assert template["spec"]["parentRefs"] == [{"name": "component"}]


def synapse_route_paths(templates):
    for template in templates:
        if template["kind"] != "HTTPRoute":
            continue
        if template["metadata"]["labels"].get("app.kubernetes.io/name") != "synapse":
            continue
        for rule in template["spec"]["rules"]:
            for match in rule["matches"]:
                yield match["path"]["value"]


def synapse_ingress_paths(templates):
    for template in templates:
        if template["kind"] != "Ingress":
            continue
        if template["metadata"]["labels"].get("app.kubernetes.io/name") != "synapse":
            continue
        for rule in template["spec"]["rules"]:
            for path in rule["http"]["paths"]:
                yield path["path"]


def haproxy_cfg(templates):
    for template in templates:
        if template["kind"] == "ConfigMap" and "haproxy.cfg" in template.get("data", {}):
            if template_to_deployable_details(template).name == "haproxy":
                return template["data"]["haproxy.cfg"]
    raise AssertionError("No HAProxy ConfigMap found")


@pytest.mark.parametrize("values_file", ["synapse-ingress-additional-paths-values.yaml"])
@pytest.mark.asyncio_cooperative
async def test_synapse_ingress_additional_paths_ignore_routes_paths(templates):
    rendered_paths = set(synapse_ingress_paths(templates))
    assert "/_matrix/identity" in rendered_paths
    assert "/_matrix/from-routes" not in rendered_paths
    config = haproxy_cfg(templates)
    assert "path_beg /other" in config
    assert "path_beg /_matrix/internal" not in config


@pytest.mark.parametrize("values_file", ["synapse-gatewayapi-additional-paths-values.yaml"])
@pytest.mark.asyncio_cooperative
async def test_synapse_routes_additional_paths_ignore_ingress_paths(templates):
    rendered_paths = set(synapse_route_paths(templates))
    assert "/_matrix/from-routes" in rendered_paths
    assert "/_matrix/identity" not in rendered_paths
    config = haproxy_cfg(templates)
    assert "path_beg /_matrix/internal" in config
    assert "path_beg /other" not in config


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_httproute_when_handler_is_none(values, make_templates):
    values["inboundTrafficHandler"] = "none"
    assert list(component_httproutes(await make_templates(values))) == []


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_handler_none_beats_global_routes(values, make_templates):
    def set_handler_none(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(values, PropertyType.InboundTrafficHandler, "none")

    iterate_deployables_ingress_parts(set_handler_none)
    assert list(component_httproutes(await make_templates(values))) == []


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_traffic_policies_by_default(templates):
    assert traffic_policies(templates, "ClientTrafficPolicy") == []
    assert traffic_policies(templates, "BackendTrafficPolicy") == []


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_global_traffic_policies_follow_httproutes(values, make_templates, release_name):
    values.setdefault("gateway", {})["create"] = True
    values["gateway"]["className"] = "test"
    values.setdefault("httpRoutes", {})["clientTrafficPolicy"] = {"timeout": {"http": {"requestTimeout": "10s"}}}
    values["httpRoutes"]["backendTrafficPolicy"] = {"retry": {"numRetries": 2}}

    rendered = await make_templates(values)
    routes = list(component_httproutes(rendered))
    client_policies = traffic_policies(rendered, "ClientTrafficPolicy")
    backend_policies = traffic_policies(rendered, "BackendTrafficPolicy")
    assert len(client_policies) == len(routes)
    assert len(backend_policies) == len(routes)
    for route in routes:
        client_policy = next(
            policy for policy in client_policies if policy["metadata"]["name"] == f"{route['metadata']['name']}-client-traffic"
        )
        backend_policy = next(
            policy
            for policy in backend_policies
            if policy["metadata"]["name"] == f"{route['metadata']['name']}-backend-traffic"
        )
        assert client_policy["spec"]["timeout"]["http"]["requestTimeout"] == "10s"
        assert client_policy["spec"]["targetRefs"] == [
            {
                "group": "gateway.networking.k8s.io",
                "kind": "Gateway",
                "name": parent_ref["name"],
                **({"sectionName": parent_ref["sectionName"]} if "sectionName" in parent_ref else {}),
            }
            for parent_ref in route["spec"]["parentRefs"]
        ]
        assert backend_policy["spec"]["retry"]["numRetries"] == 2
        assert backend_policy["spec"]["targetRefs"] == [
            {
                "group": "gateway.networking.k8s.io",
                "kind": "HTTPRoute",
                "name": route["metadata"]["name"],
            }
        ]
        assert route["metadata"]["name"].startswith(f"{release_name}-")


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_traffic_policy_overrides_global(values, make_templates):
    values.setdefault("gateway", {})["create"] = True
    values["gateway"]["className"] = "test"
    values.setdefault("httpRoutes", {})["clientTrafficPolicy"] = {"timeout": {"http": {"requestTimeout": "10s"}}}
    values["httpRoutes"]["backendTrafficPolicy"] = {"retry": {"numRetries": 2}}

    def override_policies(deployable_details: DeployableDetails):
        deployable_details.set_helm_values(
            values,
            PropertyType.HttpRoutes,
            {
                "clientTrafficPolicy": {"timeout": {"http": {"requestTimeout": "30s"}}},
                "backendTrafficPolicy": None,
            },
        )

    iterate_deployables_ingress_parts(override_policies)
    rendered = await make_templates(values)
    client_policies = traffic_policies(rendered, "ClientTrafficPolicy")
    assert client_policies
    assert traffic_policies(rendered, "BackendTrafficPolicy") == []
    for policy in client_policies:
        assert policy["spec"]["timeout"]["http"]["requestTimeout"] == "30s"

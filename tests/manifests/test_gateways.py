# Copyright 2026 Element Creations Ltd
#
# SPDX-License-Identifier: AGPL-3.0-only


import pytest

from . import DeployableDetails, PropertyType, gatewayapi_values_files_to_test, values_files_to_test
from .test_httproutes import component_httproutes, component_is_redirect, expected_route_hosts
from .utils import iterate_deployables_ingress_parts


def listener_name(host: str, protocol: str) -> str:
    label = host.lower().replace("*", "wildcard").replace("_", "-")
    return f"{protocol}-{label}"[:253].rstrip("-")


def tls_secret_name(release_name: str, host: str) -> str:
    label = host.lower().replace("*", "wildcard").replace("_", "-").replace(".", "-")
    return f"{release_name}-{label}-tls"[:253].rstrip("-")


def enable_gateway(values):
    values.setdefault("gateway", {})["create"] = True
    values["gateway"]["className"] = "test"


def gateways(templates):
    return [template for template in templates if template["kind"] == "Gateway"]


def redirect_routes(templates):
    return [template for template in templates if template["kind"] == "HTTPRoute" and component_is_redirect(template)]


@pytest.mark.parametrize("values_file", values_files_to_test | gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_no_gateway_by_default(templates):
    assert gateways(templates) == []


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_gateway_listeners_follow_route_hosts(values, make_templates, release_name):
    enable_gateway(values)
    hosts = sorted(set(expected_route_hosts(values)))
    # gateway.create with no route host fails chart validation.
    if not hosts:
        return

    rendered = await make_templates(values)
    found = gateways(rendered)
    assert len(found) == 1
    gateway = found[0]
    assert gateway["metadata"]["name"] == f"{release_name}-gateway"
    assert gateway["spec"]["gatewayClassName"] == "test"

    listeners = gateway["spec"]["listeners"]
    http_listeners = [listener for listener in listeners if listener["protocol"] == "HTTP"]
    https_listeners = [listener for listener in listeners if listener["protocol"] == "HTTPS"]
    assert sorted(listener["hostname"] for listener in http_listeners) == hosts
    assert sorted(listener["hostname"] for listener in https_listeners) == hosts
    for listener in http_listeners:
        assert listener["port"] == 80
        assert listener["name"] == listener_name(listener["hostname"], "http")
    for listener in https_listeners:
        assert listener["port"] == 443
        assert listener["name"] == listener_name(listener["hostname"], "https")
        assert listener["tls"]["mode"] == "Terminate"
        assert listener["tls"]["certificateRefs"][0]["name"] == tls_secret_name(release_name, listener["hostname"])

    redirects = redirect_routes(rendered)
    # One redirect HTTPRoute per component, so a shared hostname appears once per route.
    assert sorted(route["spec"]["hostnames"][0] for route in redirects) == sorted(expected_route_hosts(values))
    for route in redirects:
        host = route["spec"]["hostnames"][0]
        assert route["spec"]["parentRefs"] == [
            {"name": f"{release_name}-gateway", "sectionName": listener_name(host, "http")}
        ]
        assert route["spec"]["rules"][0]["filters"][0]["requestRedirect"]["scheme"] == "https"
        assert route["spec"]["rules"][0]["filters"][0]["requestRedirect"]["statusCode"] == 301

    for route in component_httproutes(rendered):
        host = route["spec"]["hostnames"][0]
        assert route["spec"]["parentRefs"] == [
            {"name": f"{release_name}-gateway", "sectionName": listener_name(host, "https")}
        ]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_gateway_tls_secret_beats_generated_name(values, make_templates):
    enable_gateway(values)
    if not expected_route_hosts(values):
        return
    values["gateway"]["tlsSecret"] = "shared-tls"
    values["certManager"] = {"clusterIssuer": "cluster-issuer-name"}

    rendered = await make_templates(values)
    gateway = gateways(rendered)[0]
    assert "cert-manager.io/cluster-issuer" not in gateway["metadata"].get("annotations", {})
    for listener in gateway["spec"]["listeners"]:
        if listener["protocol"] == "HTTPS":
            assert listener["tls"]["certificateRefs"][0]["name"] == "shared-tls"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_gateway_cert_manager_cluster_issuer(values, make_templates):
    enable_gateway(values)
    if not expected_route_hosts(values):
        return
    values["certManager"] = {"clusterIssuer": "cluster-issuer-name"}

    gateway = gateways(await make_templates(values))[0]
    assert gateway["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "cluster-issuer-name"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_gateway_cert_manager_issuer(values, make_templates):
    enable_gateway(values)
    if not expected_route_hosts(values):
        return
    values["certManager"] = {"issuer": "issuer-name"}

    gateway = gateways(await make_templates(values))[0]
    assert gateway["metadata"]["annotations"]["cert-manager.io/issuer"] == "issuer-name"


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_gateway_without_tls_has_http_listeners_only(values, make_templates, release_name):
    enable_gateway(values)
    if not expected_route_hosts(values):
        return
    values["gateway"]["tlsEnabled"] = False

    rendered = await make_templates(values)
    gateway = gateways(rendered)[0]
    assert {listener["protocol"] for listener in gateway["spec"]["listeners"]} == {"HTTP"}
    assert redirect_routes(rendered) == []
    for route in component_httproutes(rendered):
        host = route["spec"]["hostnames"][0]
        assert route["spec"]["parentRefs"] == [
            {"name": f"{release_name}-gateway", "sectionName": listener_name(host, "http")}
        ]


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_global_https_redirect_can_be_disabled(values, make_templates):
    enable_gateway(values)
    if not expected_route_hosts(values):
        return
    values.setdefault("httpRoutes", {})["httpsRedirect"] = False

    rendered = await make_templates(values)
    gateway = gateways(rendered)[0]
    assert {listener["protocol"] for listener in gateway["spec"]["listeners"]} == {"HTTPS"}
    assert redirect_routes(rendered) == []


@pytest.mark.parametrize("values_file", gatewayapi_values_files_to_test)
@pytest.mark.asyncio_cooperative
async def test_component_https_redirect_overrides_global(values, make_templates):
    enable_gateway(values)
    route_hosts = expected_route_hosts(values)
    if not route_hosts:
        return
    disabled_host = route_hosts[0]

    def disable_matching(deployable_details: DeployableDetails):
        if deployable_details.name == "well-known":
            component_host = values["serverName"]
        else:
            component_host = deployable_details.get_helm_values(values, PropertyType.Host, default_value="")
        if component_host == disabled_host:
            deployable_details.set_helm_values(values, PropertyType.HttpRoutes, {"httpsRedirect": False})

    iterate_deployables_ingress_parts(disable_matching)

    rendered = await make_templates(values)
    gateway = gateways(rendered)[0]
    http_hosts = sorted(listener["hostname"] for listener in gateway["spec"]["listeners"] if listener["protocol"] == "HTTP")
    https_hosts = sorted(listener["hostname"] for listener in gateway["spec"]["listeners"] if listener["protocol"] == "HTTPS")
    remaining = sorted(host for host in route_hosts if host != disabled_host)
    assert https_hosts == sorted(set(route_hosts))
    assert http_hosts == sorted(set(remaining))
    assert sorted(route["spec"]["hostnames"][0] for route in redirect_routes(rendered)) == remaining

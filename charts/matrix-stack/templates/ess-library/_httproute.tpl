{{- /*
Copyright 2026 Element Creations Ltd

SPDX-License-Identifier: AGPL-3.0-only
*/ -}}

{{- define "element-io.ess-library.http-route.annotations" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.annotations missing context" .context -}}
{{- $routes := required "element-io.ess-library.http-route.annotations context missing httpRoutes" .httpRoutes -}}
{{- $annotations := .extraAnnotations | default dict -}}
{{- $globalRoutes := $root.Values.httpRoutes | default dict -}}
{{- $annotations = mustMergeOverwrite $annotations (($globalRoutes.annotations | default dict) | deepCopy) -}}
{{- $annotations = mustMergeOverwrite $annotations (($routes.annotations | default dict) | deepCopy) -}}
{{- $cleaned := dict -}}
{{- range $key, $value := $annotations -}}
{{- if not (kindIs "invalid" $value) -}}
{{- $_ := set $cleaned $key $value -}}
{{- end -}}
{{- end -}}
{{- with $cleaned -}}
annotations:
  {{- toYaml . | nindent 2 }}
{{- end -}}
{{- end -}}
{{- end -}}

{{- /*
parentRefs come from the component httpRoutes, then the global httpRoutes.
When neither is set, gateway.create is true, and this route has a host, attach to the
generated Gateway listener for that host. sectionName matches element-io.gateway.listenerName.
*/ -}}
{{- define "element-io.ess-library.http-route.resolvedParentRefs" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.resolvedParentRefs missing context" .context -}}
{{- $routes := required "element-io.ess-library.http-route.resolvedParentRefs context missing httpRoutes" .httpRoutes -}}
{{- $host := .host | default "" -}}
{{- $globalRoutes := $root.Values.httpRoutes | default dict -}}
{{- $parentRefs := $routes.parentReferences | default $globalRoutes.parentReferences -}}
{{- if not $parentRefs -}}
{{- $gateway := $root.Values.gateway | default dict -}}
{{- if and $gateway.create $host -}}
{{- $protocol := "http" -}}
{{- if eq (include "element-io.gateway.tlsEnabled" (dict "root" $root)) "true" -}}
{{- $protocol = "https" -}}
{{- end -}}
{{- $sectionName := include "element-io.gateway.listenerName" (dict "root" $root "context" (dict "host" $host "protocol" $protocol)) -}}
{{- $parentRefs = list (dict "name" (include "element-io.gateway.name" (dict "root" $root)) "sectionName" $sectionName) -}}
{{- end -}}
{{- end -}}
{{- if $parentRefs -}}
{{- $parentRefs | toYaml -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "element-io.ess-library.http-route.parentRefs" -}}
{{- $root := .root -}}
{{- $rawParentRefs := include "element-io.ess-library.http-route.resolvedParentRefs" (dict "root" $root "context" .context) -}}
{{- if $rawParentRefs -}}
parentRefs:
{{- range $rawParentRefs | fromYamlArray }}
- name: {{ required "HTTPRoute parentRef missing name" .name | quote }}
{{- with .namespace }}
  namespace: {{ . | quote }}
{{- end }}
{{- with .group }}
  group: {{ . | quote }}
{{- end }}
{{- with .kind }}
  kind: {{ . | quote }}
{{- end }}
{{- with .sectionName }}
  sectionName: {{ . | quote }}
{{- end }}
{{- with .port }}
  port: {{ . }}
{{- end }}
{{- end }}
{{- end -}}
{{- end -}}

{{- /*
User policy settings for one httpRoutes key. The component object is merged over the global one.
null on the component skips the policy. targetRefs are not part of the user settings.
*/ -}}
{{- define "element-io.ess-library.http-route.policySettings" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.policySettings missing context" .context -}}
{{- $component := required "element-io.ess-library.http-route.policySettings missing component" .component -}}
{{- $key := required "element-io.ess-library.http-route.policySettings missing key" .key -}}
{{- $routes := $component.httpRoutes | default dict -}}
{{- $globalRoutes := $root.Values.httpRoutes | default dict -}}
{{- $disabled := and (hasKey $routes $key) (kindIs "invalid" (index $routes $key)) -}}
{{- if not $disabled -}}
{{- $merged := dict -}}
{{- if and (hasKey $globalRoutes $key) (not (kindIs "invalid" (index $globalRoutes $key))) -}}
{{- $merged = index $globalRoutes $key | deepCopy -}}
{{- end -}}
{{- if and (hasKey $routes $key) (not (kindIs "invalid" (index $routes $key))) -}}
{{- $merged = mustMergeOverwrite $merged (index $routes $key | deepCopy) -}}
{{- end -}}
{{- $settings := dict -}}
{{- range $setting, $value := $merged -}}
{{- if and (not (has $setting (list "targetRef" "targetRefs" "targetSelectors"))) (not (kindIs "invalid" $value)) -}}
{{- $_ := set $settings $setting $value -}}
{{- end -}}
{{- end -}}
{{- if $settings -}}
{{- $settings | toYaml -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "element-io.ess-library.http-route.trafficPolicies" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.trafficPolicies missing context" .context -}}
{{- $component := required "element-io.ess-library.http-route.trafficPolicies missing component" .component -}}
{{- $routeName := required "element-io.ess-library.http-route.trafficPolicies missing routeName" .routeName -}}
{{- $labels := required "element-io.ess-library.http-route.trafficPolicies missing labels" .labels -}}
{{- $host := .host | default "" -}}
{{- $clientSettings := include "element-io.ess-library.http-route.policySettings" (dict "root" $root "context" (dict "component" $component "key" "clientTrafficPolicy")) -}}
{{- if $clientSettings -}}
{{- $rawParentRefs := include "element-io.ess-library.http-route.resolvedParentRefs" (dict "root" $root "context" (dict "httpRoutes" ($component.httpRoutes | default dict) "host" $host)) -}}
{{- if $rawParentRefs -}}
{{- $targetRefs := list -}}
{{- range $rawParentRefs | fromYamlArray -}}
{{- $target := dict "group" (.group | default "gateway.networking.k8s.io") "kind" (.kind | default "Gateway") "name" (required "HTTPRoute parentRef missing name" .name) -}}
{{- with .sectionName -}}
{{- $_ := set $target "sectionName" . -}}
{{- end -}}
{{- $targetRefs = append $targetRefs $target -}}
{{- end -}}
{{- $spec := $clientSettings | fromYaml -}}
{{- $_ := set $spec "targetRefs" $targetRefs -}}
{{ print "\n---\n" }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: ClientTrafficPolicy
metadata:
  labels:
    {{- $labels | nindent 4 }}
  name: {{ $root.Release.Name }}-{{ $routeName }}-client-traffic
  namespace: {{ $root.Release.Namespace }}
spec:
  {{- toYaml $spec | nindent 2 }}
{{- end -}}
{{- end -}}
{{- $backendSettings := include "element-io.ess-library.http-route.policySettings" (dict "root" $root "context" (dict "component" $component "key" "backendTrafficPolicy")) -}}
{{- if $backendSettings -}}
{{- $spec := $backendSettings | fromYaml -}}
{{- $_ := set $spec "targetRefs" (list (dict "group" "gateway.networking.k8s.io" "kind" "HTTPRoute" "name" (printf "%s-%s" $root.Release.Name $routeName))) -}}
{{ print "\n---\n" }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  labels:
    {{- $labels | nindent 4 }}
  name: {{ $root.Release.Name }}-{{ $routeName }}-backend-traffic
  namespace: {{ $root.Release.Namespace }}
spec:
  {{- toYaml $spec | nindent 2 }}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "element-io.ess-library.http-route.manifest" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.manifest missing context" .context -}}
{{- $component := required "element-io.ess-library.http-route.manifest missing component" .component -}}
{{- $componentName := required "element-io.ess-library.http-route.manifest missing componentName" .componentName -}}
{{- $routeName := required "element-io.ess-library.http-route.manifest missing routeName" .routeName -}}
{{- $labels := required "element-io.ess-library.http-route.manifest missing labels" .labels -}}
{{- $rawHost := include "element-io.ess-library.inboundTrafficHandler.rawHost" (dict "root" $root "context" (dict "component" $component "host" .host)) -}}
{{- $renderedHost := "" -}}
{{- if $rawHost -}}
{{- $renderedHost = tpl $rawHost $root | trim -}}
{{- end -}}
{{- $extraAnnotations := .extraAnnotations | default dict -}}
{{- $render := and $component.enabled (eq (include "element-io.ess-library.inboundTrafficHandler.isEnabled" (dict "root" $root "context" (dict "component" $component "trafficHandler" "gatewayapi"))) "true") -}}
{{- if .requireHost -}}
{{- $render = and $render $renderedHost -}}
{{- end -}}
{{- if $render -}}
{{- $paths := include "element-io.ess-library.inboundTrafficHandler.publicPaths" (dict "root" $root "context" (dict "component" $component "componentName" $componentName)) | fromYamlArray }}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
{{- include "element-io.ess-library.http-route.annotations" (dict "root" $root "context" (dict "httpRoutes" ($component.httpRoutes | default dict) "extraAnnotations" $extraAnnotations)) | nindent 2 }}
  labels:
    {{- $labels | nindent 4 }}
  name: {{ $root.Release.Name }}-{{ $routeName }}
  namespace: {{ $root.Release.Namespace }}
spec:
{{- include "element-io.ess-library.http-route.parentRefs" (dict "root" $root "context" (dict "httpRoutes" ($component.httpRoutes | default dict) "host" $renderedHost)) | nindent 2 }}
{{- if $renderedHost }}
  hostnames:
  - {{ $renderedHost | quote }}
{{- end }}
  rules:
{{- range $paths }}
  - matches:
    - path:
        type: PathPrefix
        value: {{ .path | quote }}
    backendRefs:
    - name: {{ .serviceName | quote }}
      port: {{ required (printf "HTTPRoute path %s on %s requires servicePortNumber" .path $componentName) .servicePortNumber }}
{{- end }}
{{- if and $renderedHost (eq (include "element-io.gateway.httpsRedirect" (dict "root" $root "context" (dict "component" $component))) "true") (($root.Values.gateway | default dict).create) }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  labels:
    {{- $labels | nindent 4 }}
  name: {{ $root.Release.Name }}-{{ $routeName }}-redirect
  namespace: {{ $root.Release.Namespace }}
spec:
  parentRefs:
  - name: {{ include "element-io.gateway.name" (dict "root" $root) | quote }}
    sectionName: {{ include "element-io.gateway.listenerName" (dict "root" $root "context" (dict "host" $renderedHost "protocol" "http")) | quote }}
  hostnames:
  - {{ $renderedHost | quote }}
  rules:
{{- range $paths }}
  - matches:
    - path:
        type: PathPrefix
        value: {{ .path | quote }}
    filters:
    - type: RequestRedirect
      requestRedirect:
        scheme: https
        statusCode: 301
{{- end }}
{{- end }}
{{- include "element-io.ess-library.http-route.trafficPolicies" (dict "root" $root "context" (dict "component" $component "routeName" $routeName "labels" $labels "host" $renderedHost)) }}
{{- end -}}
{{- end -}}
{{- end -}}

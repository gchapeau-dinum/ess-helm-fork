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
{{- define "element-io.ess-library.http-route.parentRefs" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.http-route.parentRefs missing context" .context -}}
{{- $routes := required "element-io.ess-library.http-route.parentRefs context missing httpRoutes" .httpRoutes -}}
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
parentRefs:
{{- range $parentRefs }}
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
{{- end }}
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

{{- end -}}
{{- end -}}
{{- end -}}

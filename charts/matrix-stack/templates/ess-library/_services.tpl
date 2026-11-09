{{- /*
Copyright 2026 Element Creations Ltd

SPDX-License-Identifier: AGPL-3.0-only
*/ -}}

{{- define "element-io.ess-library.service.spec" -}}
{{- $root := .root -}}
{{- $type := "" -}}
{{- $internalTrafficPolicy := "" -}}
{{- $ipFamilyPolicy := "" -}}
{{- $externalTrafficPolicy := "" -}}
{{- $emitExternalTrafficPolicy := false -}}
{{- $externalIPs := list -}}
{{- $emitExternalIPs := false -}}
{{- $ipFamilies := list -}}
{{- $clusterIP := "" -}}
{{- if .exposedService -}}
{{- $exposedService := .exposedService -}}
{{- $type = $exposedService.portType -}}
{{- $internalTrafficPolicy = $exposedService.internalTrafficPolicy -}}
{{- $ipFamilyPolicy = $exposedService.ipFamilyPolicy | default ((eq $root.Values.networking.ipFamily "dual-stack") | ternary "PreferDualStack" "SingleStack") -}}
{{- if hasKey $exposedService "externalIPs" -}}
{{- $externalIPs = $exposedService.externalIPs -}}
{{- $emitExternalIPs = true -}}
{{- end -}}
{{- with $exposedService.ipFamilies -}}
{{- $ipFamilies = . -}}
{{- end -}}
{{- if ne $exposedService.portType "ClusterIP" -}}
{{- $externalTrafficPolicy = $exposedService.externalTrafficPolicy -}}
{{- $emitExternalTrafficPolicy = true -}}
{{- end -}}
{{- else -}}
{{- $context := required "element-io.ess-library.service.spec missing context" .context -}}
{{- $service := $context.service | default dict -}}
{{- $legacyService := dict -}}
{{- if $context.ingress -}}
{{- $legacyService = $context.ingress.service | default dict -}}
{{- end -}}
{{- $globalService := $root.Values.ingress.service -}}
{{- $type = $service.type | default $legacyService.type | default $globalService.type -}}
{{- $internalTrafficPolicy = $service.internalTrafficPolicy | default $legacyService.internalTrafficPolicy | default $globalService.internalTrafficPolicy -}}
{{- $ipFamilyPolicy = "PreferDualStack" -}}
{{- if and ($context.headlessService | default false) (eq $type "ClusterIP") -}}
{{- $clusterIP = "None" -}}
{{- end -}}
{{- if list "LoadBalancer" "NodePort" | has $type -}}
{{- $externalTrafficPolicy = $service.externalTrafficPolicy | default $legacyService.externalTrafficPolicy | default $globalService.externalTrafficPolicy -}}
{{- $emitExternalTrafficPolicy = true -}}
{{- end -}}
{{- if hasKey $service "externalIPs" -}}
{{- $externalIPs = $service.externalIPs -}}
{{- $emitExternalIPs = true -}}
{{- else if hasKey $legacyService "externalIPs" -}}
{{- $externalIPs = $legacyService.externalIPs -}}
{{- $emitExternalIPs = true -}}
{{- end -}}
{{- end -}}
type: {{ $type }}
{{- if $clusterIP }}
clusterIP: {{ $clusterIP }}
{{- end }}
{{- if $emitExternalTrafficPolicy }}
externalTrafficPolicy: {{ $externalTrafficPolicy }}
{{- end }}
{{- if $emitExternalIPs }}
externalIPs: {{ $externalIPs | toYaml | nindent 2 }}
{{- end }}
ipFamilyPolicy: {{ $ipFamilyPolicy }}
{{- with $ipFamilies }}
ipFamilies:
  {{- toYaml . | nindent 2 }}
{{- end }}
internalTrafficPolicy: {{ $internalTrafficPolicy }}
{{- end -}}

{{- define "element-io.ess-library.service.annotations" -}}
{{- $root := .root -}}
{{- with required "element-io.ess-library.service.annotations missing context" .context -}}
{{- $service := .service | default dict -}}
{{- $legacyService := dict -}}
{{- with .ingress -}}
{{- $legacyService = .service | default dict -}}
{{- end -}}
{{- $annotations := .extraAnnotations | default dict -}}
{{- $annotations = mustMergeOverwrite $annotations ($root.Values.ingress.service.annotations | deepCopy) -}}
{{- if $legacyService.annotations }}
{{- $annotations = mustMergeOverwrite $annotations ($legacyService.annotations | deepCopy) -}}
{{- end -}}
{{- if $service.annotations }}
{{- $annotations = mustMergeOverwrite $annotations ($service.annotations | deepCopy) -}}
{{- end -}}
{{- with $annotations -}}
annotations:
  {{- toYaml . | nindent 2 }}
{{- end -}}
{{- end -}}
{{- end -}}


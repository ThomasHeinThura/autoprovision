# Requirements

## If it runs in the RKE2 cluster

No new VMs. What you need is spare capacity on the existing workers.

| Size | vCPU across the cluster | RAM | Storage |
| ---- | ----------------------- | --- | ------- |
| Single node | 6 | 24 GB | Object storage (LGTM) or 250 GB via a storage class |
| High availability | 12 | 48 GB | Object storage (LGTM) or 500 GB via a storage class |

- The cluster exists and its kubeconfig is on the jump host.
- **Istio and the shared gateway are installed**, so the dashboard can be routed
  by hostname rather than a node port.
- **If you chose LGTM: object storage is up.** Loki, Tempo and Mimir each need a
  bucket before their first pod starts. Without it they crash-loop, which looks
  like a monitoring failure and is a storage failure.
- If you chose OpenSearch or Elastic: a storage class that can provision
  persistent volumes, or the StatefulSets stay `Pending` forever.

## If it runs on a Docker VM

| Size | VMs | vCPU | RAM | Disk |
| ---- | --- | ---- | --- | ---- |
| Single node | 1 | 4 | 16 GB | 250 GB |
| High availability | **3 — an odd number** | 8 | 32 GB | 500 GB each |

An odd node count, so the cluster manager can hold quorum. Two nodes cannot
arbitrate.

OpenSearch and Elasticsearch both need `vm.max_map_count` at 262144. The playbook
sets it; the error when it is missing names a memory-map limit rather than a
sysctl, which sends people the wrong way for an afternoon.

## What you must decide first

**Retention.** The default is 30 days. Longer needs proportionally more storage,
and shortening it later does not reclaim what has already been written. This is
the field worth thinking about before you click Run.

**Every log source accounted for** — both RKE2 clusters, all Docker VMs, the
database nodes, and the WSO2 gateway sidecars. A source nobody configured is a
source nobody notices until they need it.

## Ports

| Stack | Ports |
| ----- | ----- |
| LGTM | `3000` Grafana · `3100` Loki write · `4317` OTLP ingest |
| OpenSearch | `5601` Dashboards · `9200` REST · `9300` transport |
| Elastic | `5601` Kibana · `9200` REST · `5044` Logstash Beats input |

## What this does not do

- **Deploy the other two stacks.** You get the one you chose.
- **Migrate existing data.** Switching later leaves old indices where they are.
- **Back itself up.** Point Backups & DR at it once it holds data you would miss.

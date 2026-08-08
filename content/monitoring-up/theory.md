# Monitoring

## Why one stack and not three

LGTM, OpenSearch and Elastic all store and search logs. Running more than one
means every log source configured twice, retention reasoned about twice,
dashboards built twice and then diverging, and — during an incident — someone
deciding which one to trust.

The cost is not compute. It is that two sources of truth is the same as none.

So the console asks once and installs one. The comparison lives in the interface
rather than in somebody's head, and the answer is recorded in the workload's saved
configuration where the next person can find it.

## The actual trade-off

|  | LGTM | OpenSearch | Elastic |
| --- | --- | --- | --- |
| Logs | Loki — indexes labels, not content | Full-text index | Full-text index |
| Traces | Tempo, first class | Trace analytics | APM |
| Metrics | Mimir, Prometheus-compatible | Needs Prometheus separately | APM |
| Storage cost | Lowest — object storage, minimal index | High | High |
| Arbitrary text search | Weakest | Strongest | Strongest |
| Licence | AGPLv3 | Apache 2.0 | Elastic Licence / SSPL |
| Tested in this lab | No | No | **Yes** |

The real split is that **Loki indexes labels, not log content**. That is why it is
cheap to store and fast at *"show me everything from this pod in this window"*,
and comparatively poor at *"find this string anywhere in the last month"*.

If your team debugs by grepping for arbitrary strings across everything, a
full-text index earns its cost. If they debug by narrowing to a workload and
reading forward, Loki is better and cheaper. Watch how people actually work before
choosing, because both answers are defensible and only one matches your team.

## Why placement matters more than it looks

Monitoring inside the cluster is monitoring with shared fate. When the cluster is
what has broken, the tooling you would use to diagnose it is inside the broken
thing.

A separate VM costs another machine to run and patch, and keeps working during
exactly the outage you most need it for. Neither answer is wrong. The in-cluster
answer is only right if you accept that a total cluster failure gets diagnosed
from `kubectl` and `journalctl`.

## Why retention is decided now

Every one of these will fill whatever disk you give it.

Retention is not a dial you turn down later to recover space. The data is already
written; shortening the policy only stops new data accumulating. Sizing follows
from retention, which makes it the first number to settle and the last one anyone
wants to discuss.

## Why switching later is expensive

The stack is not the server. It is the shipper on every VM, the collector in every
cluster, the sidecar in the WSO2 gateway pods, the retention policy, and every
dashboard and alert anyone has built.

Changing it means touching all of them, and the historical data does not come with
you. The WSO2 gateways currently ship through a Filebeat sidecar to Logstash on
`5044`, configured in the team's own repository — so moving to LGTM means editing
that repo and redeploying the gateways.

Decide before Production is built, not after.

## Why the collector is vendor-neutral

The OpenTelemetry Collector speaks to all three. Instrumenting applications
against it rather than against a vendor SDK means the *applications* survive a
change of monitoring stack even though the platform does not. That is the one part
of this decision it is cheap to hedge, so hedge it.

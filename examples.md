# Machine specs

name                           RAM       CPUs     Disk Space     Version
ceph-mon/0                     1 GB      2        10 GB          12.2.11
ceph-mon/1                     1 GB      2        10 GB          12.2.11
ceph-mon/2                     1 GB      2        10 GB          12.2.11
ceph-osd/0                     1 GB      2        500 GB         12.2.11
ceph-osd/1                     1 GB      2        500 GB         12.2.11
ceph-osd/2                     1 GB      2        500 GB         12.2.11
etcd/0                         1 GB      2        10 GB          3.2.10
etcd/1                         1 GB      2        10 GB          3.2.10
etcd/2                         1 GB      2        10 GB          3.2.10
kubeapi-load-balancer/0        1 GB      2        10 GB          1.14.1
kubernetes-master/0            4 GB      2        16 GB          1.14.1
kubernetes-master/1            4 GB      2        16 GB          1.14.1
kubernetes-worker/0            4 GB      4        16 GB          1.14.1
kubernetes-worker/1            4 GB      4        16 GB          1.14.1
kubernetes-worker/2            4 GB      4        16 GB          1.14.1
juju-controller/0              4 GB      2        10 GB          2.5.4

# use-case

## Regular Kubernetes

* https://gitlab.ilabt.imec.be/sborny/relations-mutating-webhook
* https://gitlab.ilabt.imec.be/dataflows/cot/sse-consumer

A regular deployment requires two objects.

A configmap that contains the URL to an external SSE consumer. (required once) *Note: we can't use an `ExternalService` here because that would change the hostname field in the header of requests to the SSE consumer.*

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sse-consumer-config
data:
  BASE_URL: 'https://sse-endpoint.example.com'
```

The SSE consumer itself (required for every new consumer).

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sse-consumer
  labels:
    app: sse-consumer
spec:
  replicas: 1
  template:
    metadata:
      labels:
        app: sse-consumer
    spec:
      containers:
      - name: sse-consumer
        image: tutum/curl
        command: ["/bin/sleep", "infinity"]
        imagePullPolicy: IfNotPresent
        envFrom:
          - configMapRef:
              name: sse-consumer-config
```

## In Juju

* both fresh deploy and update possible
* Two Kubernetes charms
* Juju needed to deploy and relate

```yaml
bundle: kubernetes
applications:
  sse-endpoint:
    charm: sse-endpoint
    options:
        base-url: sse-endpoint.example.com
  sse-consumer:
    charm: sse-consumer
relations:
- - sse-endpoint
  - sse-consumer
```

## Our solution

```yaml
kind: Service
apiVersion: v1
metadata:
  name: "sse-endpoint"
  annotations:
    provides: "sse"
    BASE_URL: "sse-endpoint.example.com"
spec:
  type: ExternalName
  externalName: sse-endpoint.example.com
```

```yaml
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: "sse-consumer"
spec:
  replicas: 1
  template:
    metadata:
      annotations:
        consumes: "sse"
        relations: "sse-endpoint"
      labels:
        app: sleep
    spec:
      containers:
      - name: sleep
        image: tutum/curl
        command: ["/bin/sleep","infinity"]
        imagePullPolicy: IfNotPresent
```

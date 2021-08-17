# Tests Juju

## Setup

```bash
juju bootstrap vmware1 vmware-k8s-relations --config primary-network=V31_TENGU --config firewall-mode=none --config datastore=ZFS_NFSSTORE --bootstrap-constraints="cores=2 mem=4G" --credential mesebrec
juju model-defaults primary-network=V31_TENGU firewall-mode=none datastore=ZFS_NFSSTORE
juju deploy cs:bundle/canonical-kubernetes-471
```

followed this tutorial: https://discourse.jujucharms.com/t/tutorial-using-juju-on-charmed-kubernetes-on-vmware/1376

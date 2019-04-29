#!/usr/bin/env bash
START=2
END=200
for ((i=START;i<=END;i++)); do
    juju deploy ~/juju-build/sse-endpoint-mock enp$i
done
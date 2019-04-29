#!/usr/bin/env python3
#
# Copyright © 2019 Ghent University and imec.
# License is described in `LICENSE` file.
#
import os
import time
import json
import sys
import copy
import subprocess
from datetime import datetime

import yaml


WAIT_TIME=1
TIMEOUT=10*60


def iprint(*args, **kwargs):
    print("{}: ".format(datetime.now()), *args, file=sys.stderr, **kwargs)


def oprint(*args, **kwargs):
    print("{}, ".format(datetime.now()), *args, file=sys.stdout, **kwargs)


def get_application_pods(prefix, namespace):
    try:
        output = json.loads(subprocess.check_output(['kubectl', '-n', namespace, 'get', 'pods', '-o', 'json'], universal_newlines=True))
    except subprocess.CalledProcessError:
        iprint('Failed to get pods of namespace {}.'.format(namespace))
        return []
    # Only get application pods
    pods = [p for p in output["items"] if p["metadata"]["name"].startswith(prefix)]
    pods = [p for p in pods if p["status"]["phase"] == "Running"]
    pods = [p["metadata"]['name'] for p in pods]
    return pods


def get_num_pods_log(pods, log_snippet, namespace):
    num_pods_ok = 0
    for pod in pods:
        try:
            output = str(subprocess.check_output(['kubectl', '-n', namespace, 'logs', pod], universal_newlines=True))
        except subprocess.CalledProcessError:
            iprint('Failed to get logs of pod {}.'.format(pod))
            continue

        if log_snippet in output:
            iprint('Pod {} has "{}" in output.'.format(pod, log_snippet))
            num_pods_ok = num_pods_ok + 1
        else:
            iprint('Pod {} doesn\'t have "{}" in output. Output is "{}".'.format(pod, log_snippet, output.rstrip()))
    return num_pods_ok


def wait_until_pods_log(count, prefix, log_snippet, namespace):
    while(True):
        pods = get_application_pods(prefix, namespace)
        iprint("Found {}/{} running pods with prefix {}.".format(len(pods), count, prefix))
        if (len(pods) < count):
            time.sleep(WAIT_TIME)
            continue

        num_pods_ok = get_num_pods_log(pods, log_snippet, namespace)
        if num_pods_ok >= count:
            iprint("Found {}/{} running pods with prefix {} and log message {}.".format(num_pods_ok, count, prefix, log_snippet))
            break
        # elif num_pods_ok > count:
        #     iprint("Error: found {}/{} pods with prefix {} and log message {}.".format(num_pods_ok, count, prefix, log_snippet))
        #     exit(1)
        else:
            time.sleep(WAIT_TIME)
            continue

def time_until_ready(num_consumers, prefix, url, message, namespace):
    result = {
        "pods": {},
    }

    start_time = time.time()
    wait_until_pods_log(num_consumers, prefix, url, namespace)
    finish_time = time.time()
    elapsed_time = finish_time - start_time
    iprint( '########################################'
            '\n PODS: {}'
            '\nStarted at: {}'
            '\nFinished at: {}'
            '\nElapsed time: {}'
            ''.format(
                message,
                start_time,
                finish_time,
                elapsed_time))
    result['pods']['started'] = start_time
    result['pods']['finish'] = finish_time
    result['pods']['elapsed'] = elapsed_time
    return result


def remove_deployment(namespace):
    subprocess.check_call(['kubectl', '-n', namespace, 'delete', "-f", "temp-deployment.yaml"])


def wait_until_empty(prefix, namespace):
    start_time = time.time()

    while True and (time.time()<start_time+TIMEOUT):
        try:
            output = json.loads(subprocess.check_output(['kubectl', '-n', namespace, 'get', 'pods', '-o', 'json'], universal_newlines=True))
        except subprocess.CalledProcessError:
            iprint('Failed to get pods of namespace {}.'.format(namespace))
            continue
        pods = [p for p in output["items"] if p["metadata"]["name"].startswith(prefix)]
        pods = [p["metadata"]['name'] for p in pods]
        if (len(pods) > 0):
            iprint("Still found {} running pods with prefix {}. Waiting..".format(len(pods), prefix))
            time.sleep(WAIT_TIME)
        else:
            break


def deploy(num_consumers, prefix, namespace):
    with open('deployment.yaml') as f:
        deployment = yaml.load_all(f)
        conf = next(deployment)
        cons_template = next(deployment)

    documents = [conf]

    for i in range(0,num_consumers):
        cons_name = "sse-consumer-{}".format(i)
        cons_template["metadata"]["labels"]["app"] = cons_name
        cons_template["metadata"]["name"] = cons_name
        cons_template["spec"]["selector"]["matchLabels"]["app"] = cons_name
        cons_template["spec"]["template"]["metadata"]["labels"]["app"] = cons_name
        cons_template["spec"]["template"]["spec"]["containers"][0]["name"] = cons_name
        documents.append(copy.deepcopy(cons_template))

    with open("temp-deployment.yaml", "w") as f:
        yaml.dump_all(documents, f, default_flow_style=False)

    subprocess.check_call(['kubectl', '-n', namespace, 'apply', "-f", "temp-deployment.yaml"])


def update_base_url(prefix, namespace, base_url):
    documents = []
    with open('temp-deployment.yaml') as f:
        deployment = yaml.load_all(f)
        conf = next(deployment)
        conf["data"]["BASE_URL"] = base_url
        documents.append(conf)

        for doc in deployment:
            doc['spec']["template"]["metadata"]["labels"]["useless-label"] = base_url
            documents.append(doc)

    with open("temp-deployment.yaml", "w") as f:
        yaml.dump_all(documents, f, default_flow_style=False)
    subprocess.check_call(['kubectl', '-n', namespace, 'apply', "-f", "temp-deployment.yaml"])    


def benchmark(num_consumers, namespace):
    if not os.path.isfile('benchmark.csv'):
        with open('benchmark.csv', 'a') as f:
            f.write("namespace;num_consumers;action;event;start;end;elapsed\n")
        
    base_url = "endpoint.example.com"

    deployment_name = "sse-consumer"

    #
    # Time the deployment of the cluster with X units.
    deploy(num_consumers, deployment_name, namespace)

    result = time_until_ready(num_consumers, deployment_name, base_url, "Deploy {} consumers".format(num_consumers), namespace)

    with open("benchmark.csv", "a") as f:
#       f.write("model_name;num_consumers;action;event;start;end;elapsed\n")
        f.write("{};{};{};{};{};{};{}\n".format(
            namespace,
            num_consumers,
            "deploy",
            "pods",
            result['pods']['started'],
            result['pods']['finish'],
            result['pods']['elapsed'],
        ))
    #
    # Time that it takes to change the url.
    for i in range(1, 11):
        new_url = str(i) + base_url
        update_base_url(deployment_name, namespace, new_url)

        result = time_until_ready(num_consumers, deployment_name, new_url, "Change {} consumers".format(num_consumers), namespace)
        with open("benchmark.csv", "a") as f:
            f.write("{};{};{};{};{};{};{}\n".format(
                namespace,
                num_consumers,
                "change",
                "pods",
                result['pods']['started'],
                result['pods']['finish'],
                result['pods']['elapsed'],
            ))


    #
    # Delete model as best as we can
    remove_deployment(namespace)
    wait_until_empty(deployment_name, namespace)





namespace = "k8s-native-test"

for i in range(5, 66, 5):
    benchmark(i, namespace)


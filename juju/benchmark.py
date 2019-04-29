#!/usr/bin/env python3
#
# Copyright © 2019 Ghent University and imec.
# License is described in `LICENSE` file.
#
import os
import time
import json
import sys
import subprocess
from datetime import datetime

import yaml


WAIT_TIME=1
TIMEOUT=10*60

def check_all_ready(applications):
    for _, app_state in applications.items():
        for un_name, un_state in app_state.get('units', {}).items():
            if ("active" in un_state['workload-status']['current']
                    and "idle" in un_state['juju-status']['current']
                    and "waiting" not in un_state['workload-status'].get('message')):
                # unit is ready
                pass
            elif ("endpoint" in un_name):
                # endpoint is always ready
                pass
            else:
                # unit is NOT ready
                iprint("{} is not ready: {}".format(
                    un_name,
                    un_state['workload-status'].get('message', "")))
                return False
    iprint(yaml.dump(applications))
    return True


def iprint(*args, **kwargs):
    print("{}: ".format(datetime.now()), *args, file=sys.stderr, **kwargs)


def oprint(*args, **kwargs):
    print("{}, ".format(datetime.now()), *args, file=sys.stdout, **kwargs)


def deploy(num_consumers, prefix, modelname):
    with open('bundle.yaml') as f:
        bundle = yaml.load(f)
    
    for i in range(0,num_consumers):
        bundle["applications"]["{}{}".format(prefix, i)] = {
            # sse-consumer-1 is with storage
            # sse-consumer-2 is without storage
            "charm": "cs:~tengu-team/sse-consumer-2",
            "scale": 1,
        }
        if not bundle.get("relations"):
            bundle["relations"] = []
        bundle["relations"].append([
            "endpoint:sse-endpoint",
            "{}{}:sse-endpoint".format(prefix, i),
        ])

    with open("temp-bundle.yaml", "w") as f:
        yaml.dump(bundle, f, default_flow_style=False)
    subprocess.check_call(['juju', 'deploy', './temp-bundle.yaml', '-m', modelname])


def get_application_pods(prefix, modelname):
    try:
        output = json.loads(subprocess.check_output(['kubectl', '-n', modelname, 'get', 'pods', '-o', 'json'], universal_newlines=True))
    except subprocess.CalledProcessError:
        iprint('Failed to get pods of namespace {}.'.format(modelname))
        return []
    # Only get application pods
    pods = [p for p in output["items"] if p["metadata"]["labels"].get("juju-application", "").startswith(prefix)]
    pods = [p for p in pods if p["status"]["phase"] == "Running"]
    pods = [p["metadata"]['name'] for p in pods]
    return pods


def get_num_pods_log(pods, log_snippet, modelname):
    num_pods_ok = 0
    for pod in pods:
        try:
            output = str(subprocess.check_output(['kubectl', '-n', modelname, 'logs', pod], universal_newlines=True))
        except subprocess.CalledProcessError:
            iprint('Failed to get logs of pod {}.'.format(pod))
            continue

        if log_snippet in output:
            iprint('Pod {} has "{}" in output.'.format(pod, log_snippet))
            num_pods_ok = num_pods_ok + 1
        else:
            iprint('Pod {} doesn\'t have "{}" in output. Output is "{}".'.format(pod, log_snippet, output.rstrip()))
    return num_pods_ok


def wait_until_pods_log(count, prefix, log_snippet, modelname):
    while(True):
        pods = get_application_pods(prefix, modelname)
        iprint("Found {}/{} running pods with prefix {}.".format(len(pods), count, prefix))
        if (len(pods) < count):
            time.sleep(WAIT_TIME)
            continue

        num_pods_ok = get_num_pods_log(pods, log_snippet, modelname)
        if num_pods_ok == count:
            iprint("Found {}/{} running pods with prefix {} and log message {}.".format(num_pods_ok, count, prefix, log_snippet))
            break
        elif num_pods_ok > count:
            iprint("Error: found {}/{} pods with prefix {} and log message {}.".format(num_pods_ok, count, prefix, log_snippet))
            exit(1)
        else:
            time.sleep(WAIT_TIME)
            continue


def wait_until_ready(modelname):
    ready = False
    while not ready:
        time.sleep(WAIT_TIME)
        status = json.loads(subprocess.check_output(
            ['juju', 'status', '--format', 'json', '-m', modelname], universal_newlines=True))
        ready = check_all_ready(status['applications'])


def time_until_ready(num_consumers, prefix, url, message, modelname):
    result = {
        "pods": {},
        "juju": {},
    }

    start_time = time.time()
    wait_until_pods_log(num_consumers, prefix, url, modelname)
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

    wait_until_ready(modelname)
    finish_time = time.time()
    elapsed_time = finish_time - start_time
    iprint( '########################################'
            '\n UNITS: {}'
            '\nStarted at: {}'
            '\nFinished at: {}'
            '\nElapsed time: {}'
            ''.format(
                message,
                start_time,
                finish_time,
                elapsed_time))
    result['juju']['started'] = start_time
    result['juju']['finish'] = finish_time
    result['juju']['elapsed'] = elapsed_time
    return result


def clear_model(modelname):
    iprint("Clearing model {}".format(modelname))
    status = json.loads(subprocess.check_output(
        ['juju', 'status', '--format', 'json', '-m', modelname], universal_newlines=True))
    applications = status['applications'].keys()
    if applications:
        subprocess.check_call(['juju', 'remove-application', *applications, '-m', modelname])
    machines = status['machines'].keys()
    if machines:
        subprocess.check_call(['juju', 'remove-machine', *machines, '-m', modelname])


def wait_until_empty(prefix, modelname):
    start_time = time.time()

    while True and (time.time()<start_time+TIMEOUT):
        time.sleep(WAIT_TIME)
        status = json.loads(subprocess.check_output(
            ['juju', 'status', '--format', 'json', '-m', modelname], universal_newlines=True))
        if (not status['applications']) and (not status['machines']):
            break
    while True and (time.time()<start_time+TIMEOUT):
        try:
            output = json.loads(subprocess.check_output(['kubectl', '-n', modelname, 'get', 'pods', '-o', 'json'], universal_newlines=True))
        except subprocess.CalledProcessError:
            iprint('Failed to get pods of namespace {}.'.format(modelname))
            continue
        pods = [p for p in output["items"] if p["metadata"]["labels"].get("juju-application", "").startswith(prefix)]
        pods = [p["metadata"]['name'] for p in pods]
        if (len(pods) > 0):
            iprint("Still found {} running pods with prefix {}. Waiting..".format(len(pods), prefix))
            time.sleep(WAIT_TIME)
        else:
            break


def benchmark(num_consumers, modelname):
    if not os.path.isfile('benchmark.csv'):
        with open('benchmark.csv', 'a') as f:
            f.write("model_name;num_consumers;action;event;start;end;elapsed\n")
        

    prefix = "consumer"
    base_url = "endpoint.example.com"

    subprocess.check_call(['juju', 'add-model', modelname, 'k8s-relations-k8s'])
    # clear_model()
    # wait_until_empty(prefix)

    #
    # Time the deployment of the cluster with X units.
    deploy(num_consumers, prefix, modelname)
    result = time_until_ready(num_consumers, prefix, base_url, "Deploy {} consumers".format(num_consumers), modelname)

    with open("benchmark.csv", "a") as f:
#       f.write("model_name;num_consumers;action;event;start;end;elapsed\n")
        f.write("{};{};{};{};{};{};{}\n".format(
            modelname,
            num_consumers,
            "deploy",
            "pods",
            result['pods']['started'],
            result['pods']['finish'],
            result['pods']['elapsed'],
        ))
        f.write("{};{};{};{};{};{};{}\n".format(
            modelname,
            num_consumers,
            "deploy",
            "juju",
            result['juju']['started'],
            result['juju']['finish'],
            result['juju']['elapsed'],
        ))
    #
    # Time that it takes to change the url.
    for i in range(1, 11):
        new_url = str(i) + base_url
        subprocess.check_call([
            'juju',
            'config',
            '-m',
            modelname,
            'endpoint',
            'base-url={}'.format(new_url)])
        result = time_until_ready(num_consumers, prefix, new_url, "Change {} consumers".format(num_consumers), modelname)
        with open("benchmark.csv", "a") as f:
    #       f.write("model_name;num_consumers;action;event;start;end;elapsed\n")
            f.write("{};{};{};{};{};{};{}\n".format(
                modelname,
                num_consumers,
                "change",
                "pods",
                result['pods']['started'],
                result['pods']['finish'],
                result['pods']['elapsed'],
            ))
            f.write("{};{};{};{};{};{};{}\n".format(
                modelname,
                num_consumers,
                "change",
                "juju",
                result['juju']['started'],
                result['juju']['finish'],
                result['juju']['elapsed'],
            ))

    #
    # Delete model as best as we can
    clear_model(modelname)
    wait_until_empty(prefix, modelname)



for i in range(45, 51, 5):
    benchmark(i, "k8s-test4-"+ str(i))


#wait_until_empty("consumer", "k8s-test")



# benchmark(2, "k8s-test-2")


# clear_model("k8s-test3-45")
# wait_until_empty("consumer","k8s-test2-25")
# deploy(count, prefix)    
# wait_until_pods_log(count, prefix, base_url)



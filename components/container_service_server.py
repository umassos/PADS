import grpc
from concurrent import futures
import container_service_pb2 as pb2
import container_service_pb2_grpc as pb2_grpc
import argparse
import subprocess
import re
import timeit
    
class CPUTimer():
    def __init__(self, cpu_time, query_time):
        self.cpu_time = cpu_time
        self.query_time = query_time

cpu_timer = CPUTimer(0, 0)

per_container_cpu_usage = {}

# A class for handling controller generator service
class ContainerService(pb2_grpc.ContainerServiceServicer):
    # Implementation of interface method defined in proto file.
    def retrieve_container_core_information(self, request, context):
        return pb2.Core_Information_Output(number_of_cores=return_core_information(request.domain_name))
    
    def retrieve_container_core_usage_limit_information(self, request, context):
        return pb2.Core_Usage_Limit_Information_Output(core_usage_limit=return_core_usage_limit_information(request.domain_name))

    def retrieve_container_cpu_usage_information(self, request, context):
        return pb2.CPU_Usage_Output(cpu_usage=return_cpu_usage_information(request.domain_name))
    
    def retrieve_cpu_freq_information(self, request, context):
        return pb2.CPU_Freq_Output(cpu_freq=return_cpu_freq(request.domain_name))


def return_core_information(domain_name):
    proc1 = subprocess.run(['lxc', 'config', 'show', domain_name], stdout=subprocess.PIPE)
    proc2 = subprocess.run(['grep', 'limits.cpu:'], input=proc1.stdout, stdout=subprocess.PIPE)
    proc3 = subprocess.run(['awk', '{print $2}'], input=proc2.stdout, stdout=subprocess.PIPE)
    # proc4 = subprocess.run(['tr', '-d' "'\"\'"], input=proc3.stdout, stdout=subprocess.PIPE)

    out = re.findall(r'\d+', str(proc3.stdout))

    if (len(out) == 1):
        return int(out[0])

    if len(out) == 2:
        if out[0] == out[1]:
            return 1

    # return int(out[0])
    return len(out)


def return_core_usage_limit_information(domain_name):
    proc1 = subprocess.run(['lxc', 'config', 'show', domain_name], stdout=subprocess.PIPE)
    proc2 = subprocess.run(['grep', 'limits.cpu.allowance:'], input=proc1.stdout, stdout=subprocess.PIPE)
    proc3 = subprocess.run(['awk', '{print $2}'], input=proc2.stdout, stdout=subprocess.PIPE)
    # proc4 = subprocess.run(['tr', '-d' "'\"\'"], input=proc3.stdout, stdout=subprocess.PIPE)

    out = re.findall(r'\d+', str(proc3.stdout))
    
    return str(out[0]) + "/" + str(out[1])
    # return str(out[0])


def return_cpu_freq(domain_name):
    proc1 = subprocess.run(['lscpu'], stdout=subprocess.PIPE)
    proc2 = subprocess.run(['grep', 'MHz'], input=proc1.stdout, stdout=subprocess.PIPE)
    proc3 = subprocess.run(['head', '-1'], input=proc2.stdout, stdout=subprocess.PIPE)
    proc4 = subprocess.run(['awk', '{print $3}'], input=proc3.stdout, stdout=subprocess.PIPE)

    return float(proc4.stdout)


def return_cpu_time(domain_name):
    proc1 = subprocess.run(['lxc', 'info', domain_name, '--resources'], stdout=subprocess.PIPE)
    proc2 = subprocess.run(['grep', 'CPU usage ('], input=proc1.stdout, stdout=subprocess.PIPE)
    proc3 = subprocess.run(['awk', '{print $5}'], input=proc2.stdout, stdout=subprocess.PIPE)

    return int(proc3.stdout)


# This works for multiple running containers
def return_cpu_usage_information(domain_name):
    if domain_name not in per_container_cpu_usage:
        last_query_time = cpu_timer.query_time
        last_cpu_time = cpu_timer.cpu_time

    else:
        last_query_time = per_container_cpu_usage[domain_name].query_time
        last_cpu_time = per_container_cpu_usage[domain_name].cpu_time

    current_query_time = timeit.default_timer()
    current_cpu_time = return_cpu_time(domain_name)

    time_interval = current_query_time - last_query_time

    current_core_info = return_core_information(domain_name)

    cpu_usage = (current_cpu_time - last_cpu_time) / (time_interval * current_core_info)

    per_container_cpu_usage[domain_name] = CPUTimer(current_cpu_time, current_query_time)

    return min(1.0, round(cpu_usage, 2))


def serve(host, port, max_workers):    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_ContainerServiceServicer_to_server(ContainerService(), server)
    ''' 
    For using the insecure port
    '''
    server.add_insecure_port(f"[::]:{port}")
    # server.add_insecure_port(f"{host}:{port}")
    '''
    For using the secure port
    '''
    # with open("/Users/msavasci/Desktop/key-new.pem", 'rb') as f:
    #     private_key = f.read()
    # with open("/Users/msavasci/Desktop/certificate.pem", 'rb') as f:
    #     certificate_chain = f.read()
    
    # credentials = grpc.ssl_server_credentials( ( (private_key, certificate_chain,), ) )

    # # server.add_secure_port(f"[::]:{port}", credentials)
    # server.add_secure_port(f"{host}:{port}", credentials)
    server.start()
    print(f"Container Service started on port {port} with {max_workers} workers.")
    server.wait_for_termination()
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Container Service Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-H", "--host", default="0.0.0.0",
                        help="Network host")
    parser.add_argument("-p", "--port", type=int, default=8089,
                        help="Network port")
    parser.add_argument("-w", "--workers", default=10,
                        type=int, help="Max Number of workers")

    args = parser.parse_args()

    serve(args.host, args.port, args.workers)
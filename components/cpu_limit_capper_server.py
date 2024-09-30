import grpc
from concurrent import futures
import cpu_limit_capper_pb2 as pb2
import cpu_limit_capper_pb2_grpc as pb2_grpc
import argparse
import subprocess

# A class for handling controller generator service
class CpuLimitCapper(pb2_grpc.CpuLimitCapperServicer):
    # Implementation of interface methods defined in proto file.
    def limit_core_number(self, request, context):
        print(f"To be allocated core: {request.number_of_cores}")
        subprocess.run(['lxc', 'config', 'set', request.domain_name, 'limits.cpu', str(request.number_of_cores)], stdout=subprocess.PIPE)
        print(f"{request.domain_name} can see and use {request.number_of_cores} cores")

        return pb2.Core_Output(status=True)
    
    def limit_core_usage(self, request, context):
        print(f"Core usage restriction: {request.core_usage_limit}")
        subprocess.run(['lxc', 'config', 'set', request.domain_name, 'limits.cpu.allowance', str(request.core_usage_limit) + "ms/100ms"], stdout=subprocess.PIPE)
        print(f"The load {request.domain_name} can put is restricted to {request.core_usage_limit}ms/100ms")

        return pb2.Core_Output(status=True)
    

def serve(host, port, max_workers):    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_CpuLimitCapperServicer_to_server(CpuLimitCapper(), server)
    ''' 
    For using the insecure port
    '''
    server.add_insecure_port(f"[::]:{port}")
    # server.add_insecure_port(f"{host}:{port}")
    '''
    For using the secure port
    '''
    server.start()
    print(f"CPU Limit Capper Server started on port {port} with {max_workers} workers.")
    server.wait_for_termination()
   

if __name__ == "__main__":
    # os.environ["LXD_DIR"] = "/var/lib/lxd"
    parser = argparse.ArgumentParser(
        description="CPU Limit Capper Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument("-H", "--host", default="0.0.0.0",
                        help="Network host")
    
    parser.add_argument("-p", "--port", type=int, default=8090,
                        help="Network port")
    
    parser.add_argument("-w", "--workers", default=10,
                        type=int, help="Max number of workers")

    parser.add_argument("-d", "--domain", default="mediawiki-51-1",
                        help="Default container")
    
    parser.add_argument("-c", "--cores", default=16,
                        type=int, help="Default number of cores")
    
    parser.add_argument("-u", "--usage", default="1600ms/100ms",
                        help="Default core usage")
    
    args = parser.parse_args()

    subprocess.run(['lxc', 'config', 'set', args.domain, 'limits.cpu', str(args.cores)], stdout=subprocess.PIPE)
    subprocess.run(['lxc', 'config', 'set', args.domain, 'limits.cpu.allowance', args.usage], stdout=subprocess.PIPE)

    print(f"Container {args.domain} is initialized with {args.cores} cores and {args.usage} core usage.")

    serve(args.host, args.port, args.workers)
import grpc
from concurrent import futures
import rapl_power_monitor_per_socket_pb2 as pb2
import rapl_power_monitor_per_socket_pb2_grpc as pb2_grpc
import argparse
import pickle
import rapl

class PowerMeasurement():
    def __init__(self, power_sample):
        self.power_sample = power_sample

measurement = PowerMeasurement( pickle.dumps(rapl.RAPLMonitor.sample()) )

# A class for handling power tools service
class PowerMonitor(pb2_grpc.PowerMonitorServicer):
    # Implementation of interface method defined in proto file.
    def per_socket_power(self, request, context):
        current_sample = pickle.dumps(rapl.RAPLMonitor.sample())

        diff = pickle.loads(current_sample) - pickle.loads(measurement.power_sample)
        tmp_list = []

        for d in diff.domains:
            domain = diff.domains[d]
            domain_name = domain.name
            power = diff.average_power(package=domain_name)
            tmp_list.append(str(domain_name))
            tmp_list.append(str(power))

        measurement.power_sample = current_sample

        my_string = ",".join(f'"{element}"' for element in tmp_list)
        
        # return pb2.Power_Output(power_value=round(avg/2, 2))
        return pb2.Power_Output(power_values=my_string)

    def write_to_file(self, request, context):
        with open(request.file_name, "w") as file:
            file.write(request.power_values)
            
            return pb2.Write_Output(status=True)


def serve(port, max_workers):
   server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
   pb2_grpc.add_PowerMonitorServicer_to_server(PowerMonitor(), server)
   server.add_insecure_port(f"[::]:{port}")
   server.start()
   print(f"Power Monitor Server started on port {port} with {max_workers} workers.")
   server.wait_for_termination()
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Power Monitor Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-p", "--port", type=int, default=8091,
                        help="Network port")
    parser.add_argument("-w", "--workers", default=10,
                        type=int, help="Max Number of workers")

    args = parser.parse_args()

    serve(args.port, args.workers)
#!/bin/bash
haproxy_log_file="/var/log/haproxy.log"
python_venv_path="/workspace1/PoVerScaler_venv/bin/python" 

script_folder_path="/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/pars/src/"
saved_data_path="/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/Experiment-24/"

manager_file_name="cluster_manager.py"

mean_response_time_file="meanResponseTimes"
tail_response_time_file="tailResponseTimes"
filtered_response_time_file="filteredResponseTimes"
log_file="logData"
error="errors"
drop="dropRate"
estimated_request="estimatedNumberOfRequests"
allocated_number_of_core_file="allocatedNumberOfCores"
allocated_core_bandwidth_file="allocatedCoreBandwidth"
measured_cpu_power_file="cpuPower"
measured_server_power_file="serverPower"
cpu_utilization_file="cpuUtil"
service_rate="serviceRate"
cpu_frequency_file="cpuFreq"

extension=".csv"
extension1=".pkl"

sudo PYTHONPATH=$PYTHONPATH $python_venv_path ${script_folder_path}${manager_file_name} -ap /gw -ts 200 -sl $haproxy_log_file -mrt ${saved_data_path}${mean_response_time_file}${extension} -trt ${saved_data_path}${tail_response_time_file}${extension} -frt ${saved_data_path}${filtered_response_time_file}${extension} -lf ${saved_data_path}${log_file}${extension1} -ev ${saved_data_path}${error}${extension} -dp ${saved_data_path}${drop}${extension} -er ${saved_data_path}${estimated_request}${extension} -anc ${saved_data_path}${allocated_number_of_core_file}${extension} -cp ${saved_data_path}${measured_cpu_power_file}${extension} -sp ${saved_data_path}${measured_server_power_file}${extension} -ac ${saved_data_path}${allocated_core_bandwidth_file}${extension} -cu ${saved_data_path}${cpu_utilization_file}${extension} -sr ${saved_data_path}${service_rate}${extension} -cf ${saved_data_path}${cpu_frequency_file}${extension}
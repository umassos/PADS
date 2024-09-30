#!/bin/bash
haproxy_log_file="/var/log/haproxy.log"
python_venv_path="/workspace1/PoVerScaler_venv/bin/python" 

script_folder_path="/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/monitoring/"
saved_data_path="/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/Motivation/Experiment-1/"

manager_file_name="interactive_ls_monitor.py"

mean_response_time_file="meanResponseTimes"
tail_response_time_file="tailResponseTimes"
error="errors"
estimated_request="estimatedNumberOfRequests"
drop="dropRate"
service_rate="serviceRate"
log_file="logData"

allocated_number_of_core_file="allocatedNumberOfCores"
allocated_core_bandwidth_file="allocatedCoreBandwidth"

measured_cpu_power_file="cpuPower"
measured_server_power_file="serverPower"
cpu_utilization_file="cpuUtil"
cpu_frequency_file="cpuFreq"

extension=".csv"
extension1=".pkl"

sudo PYTHONPATH=$PYTHONPATH $python_venv_path ${script_folder_path}${manager_file_name} -llf $haproxy_log_file -lts 200 -mrt ${saved_data_path}${mean_response_time_file}${extension} -trt ${saved_data_path}${tail_response_time_file}${extension} -ev ${saved_data_path}${error}${extension} -er ${saved_data_path}${estimated_request}${extension} -dp ${saved_data_path}${drop}${extension} -sr ${saved_data_path}${service_rate}${extension} -lf ${saved_data_path}${log_file}${extension1} -anc ${saved_data_path}${allocated_number_of_core_file}${extension} -acb ${saved_data_path}${allocated_core_bandwidth_file}${extension} -cp ${saved_data_path}${measured_cpu_power_file}${extension} -sp ${saved_data_path}${measured_server_power_file}${extension} -cf ${saved_data_path}${cpu_frequency_file}${extension} -cu ${saved_data_path}${cpu_utilization_file}${extension}
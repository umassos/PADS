#!/bin/bash
haproxy_log_file="/var/log/haproxy.log"
blast_log_file="/nfs/obelix/raid2/msavasci/workflows/blast/TigresBlast-235-16-DISTRIBUTE_PROCESS.log"
python_venv_path="/workspace1/PoVerScaler_venv/bin/python" 

script_folder_path="/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/baselines/"
saved_data_path="/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/IGSC24/Baselines/Experiment-1/"

manager_file_name="thunderbolt.py"

mean_response_time_file="meanResponseTimes"
tail_response_time_file="tailResponseTimes"
error="errors"
estimated_request="estimatedNumberOfRequests"
actual_request="actualNumberOfRequests"
drop="dropRate"
service_rate="serviceRate"
log_file="logData"

curr_progress="iterationProgress"
overall_progress_percentage="progressPercentage"

measured_cpu_power_file="cpuPower"
measured_server_power_file="serverPower"
cpu_utilization_file="cpuUtil"
cpu_frequency_file="cpuFreq"

allocated_core_bandwidth_file="allocatedCoreQuota"
power_cap_file="powerCapValues"
system_decision="systemDecision"

extension=".csv"
extension1=".pkl"

sudo PYTHONPATH=$PYTHONPATH $python_venv_path ${script_folder_path}${manager_file_name} -llf $haproxy_log_file -lts 200 -mrt ${saved_data_path}${mean_response_time_file}${extension} -trt ${saved_data_path}${tail_response_time_file}${extension} -ev ${saved_data_path}${error}${extension} -er ${saved_data_path}${estimated_request}${extension} -ar ${saved_data_path}${actual_request}${extension} -dp ${saved_data_path}${drop}${extension} -sr ${saved_data_path}${service_rate}${extension} -lf ${saved_data_path}${log_file}${extension1} -blf $blast_log_file -bts 235 -ip ${saved_data_path}${curr_progress}${extension} -pp ${saved_data_path}${overall_progress_percentage}${extension} -cp ${saved_data_path}${measured_cpu_power_file}${extension} -sp ${saved_data_path}${measured_server_power_file}${extension} -cf ${saved_data_path}${cpu_frequency_file}${extension} -cu ${saved_data_path}${cpu_utilization_file}${extension} -acq ${saved_data_path}${allocated_core_bandwidth_file}${extension} -pc ${saved_data_path}${power_cap_file}${extension} -sd ${saved_data_path}${system_decision}${extension}
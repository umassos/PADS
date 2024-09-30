#!/bin/bash
haproxy_log_file="/var/log/haproxy.log"
blast_log_file="/nfs/obelix/raid2/msavasci/workflows/blast/TigresBlast-235-16-DISTRIBUTE_PROCESS.log"
python_venv_path="/workspace1/PoVerScaler_venv/bin/python" 

script_folder_path="/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/monitoring/"
saved_data_path="/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/Motivation/Experiment-1/"

manager_file_name="interactive_batch_application_monitor.py"

curr_progress="iterationProgress"
overall_progress_percentage="progressPercentage"
allocated_number_of_core_file="allocatedNumberOfCores"
allocated_core_bandwidth_file="allocatedCoreBandwidth"

measured_cpu_power_file="cpuPower"
measured_server_power_file="serverPower"
cpu_utilization_file="cpuUtil"
cpu_frequency_file="cpuFreq"

extension=".csv"

sudo PYTHONPATH=$PYTHONPATH $python_venv_path ${script_folder_path}${manager_file_name} -blf $blast_log_file -bts 235 -ip ${saved_data_path}${curr_progress}${extension} -pp ${saved_data_path}${overall_progress_percentage}${extension} -anc ${saved_data_path}${allocated_number_of_core_file}${extension} -acb ${saved_data_path}${allocated_core_bandwidth_file}${extension} -cp ${saved_data_path}${measured_cpu_power_file}${extension} -sp ${saved_data_path}${measured_server_power_file}${extension} -cf ${saved_data_path}${cpu_frequency_file}${extension} -cu ${saved_data_path}${cpu_utilization_file}${extension}
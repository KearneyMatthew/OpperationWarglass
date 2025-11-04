# OpperationWarglass
This project attempts to use artificial intelligence to simulate a red-versus-blue computer battle, where red acts as a malicious actor seeking to gain access to or steal files from a blue server. In this simulation, the artificial intelligence would control the actions of the red virtual machine and then also control the blue virtual machine.

aggregate_runs.py: This files job is to take in the files that are created by both virtual machines and adds them into a directory called run and then gives it a specialized names
ai_agent_codellama.py: This is where the prompts are given to the artificial inteligence and then the responses are placed into json format and placed into a runnable command
app.py: This is the interaction between the html file and the orchestrator_stub.py the point of this is to take in the inputs and places it to orchestrator_stub.py
auto_log_aggragator.py: This is the second step in the aggregate log procces this is where the logs are taken from the computers and given to the aggregate_runs.py
blue_detection_agent.py: This file is constantly run on the blue Vm and is there to attempt to see when the blue vm is being attacked.
command_logger_simple.py: This file is going to log all commands that the orchestrator_stub.py comes out with and attempts to run.
index.html: This is teh website and has had a lot of time spent on ensuring it looks very nice.
orchestrator_stub.py: This is the breain of the operation and will take in the inputs through app.py and then will itterate through the order by order.yaml after that it will start grabbing the prompts from promts.yaml and then will grab the responses and place them into the log files after that will continue through until all parts have been completed.
order.yaml: This holds the order of the attacks as the ai was unable to complete this on its own.
prompts.yaml:This file holds all of the prompts that will be given to the ai.
red_vs_blue_config.yaml: This holds all of the virtual Machine information like the ip addresses.
simulationCheckList.sh: This is used as a way to check for all of the files required for the simulation.
ssh_exec.py: This is the way in which the control vm can connect and execute commands on the otehr virtual machines
whitelist.yaml: This file that holds all of the commands the virtual machine can run along with the ips it can run it on.
whitelist_validator.py: This file is used to check if the command that was given is able to run and looks at the commmand and compares it to the whitelist.yaml.

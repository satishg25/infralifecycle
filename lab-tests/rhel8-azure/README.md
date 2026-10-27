
# RHEL 8.10 lab test (Azure, key-based SSH)



Run on the Ansible controller: `TARGET=<ip> ANSIBLE_USER=<user> ./infralifecycle-test.sh bootstrap|preflight|tomcat|apache`



| Use case | Result (ansible-core 2.16.19) |

|---|---|

| tomcat_standalone | Pass: re-apply changed=0, /health/ 200 |

| apache_standalone | Pass: re-apply changed=0, /health/ 200, TRACE 405 |

| tomcat_ha, apache_ha | Not tested (need 2+ nodes) |



Not covered: SELinux enforcing, firewalld active, run_baseline, run_os_validation.

Requires: passwordless sudo and SSH key on the target; controller needs python3.11.


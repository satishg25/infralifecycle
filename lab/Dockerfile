# Lab node: Rocky Linux (RHEL rebuild) with systemd and sshd, managed like a VM. LAB ONLY - the
# containers run privileged so systemd, firewall-free networking and Pacemaker's IPaddr2 work.
# No Python is added: Ansible discovers the platform Python, exactly as on a RHEL host.
ARG ROCKY_VERSION=8
FROM rockylinux/rockylinux:${ROCKY_VERSION}
RUN dnf -y install systemd openssh-server sudo iproute procps-ng tar gzip which \
 && dnf clean all \
 && systemctl enable sshd \
 && useradd -m -s /bin/bash ansible \
 && echo "ansible ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ansible \
 && chmod 0440 /etc/sudoers.d/ansible
# run.sh puts your public key here (the file is git-ignored).
COPY --chown=ansible:ansible .build/authorized_keys /home/ansible/.ssh/authorized_keys
RUN chmod 700 /home/ansible/.ssh && chmod 600 /home/ansible/.ssh/authorized_keys
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]

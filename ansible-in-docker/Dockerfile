FROM rockylinux:9-minimal

ENV ANSIBLE_COLLECTIONS_PATHS=/opt/ansible_collections \
    PATH=/opt/ansible_venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    DOCKER_BUILDKIT=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN set -ex \
    && microdnf install -y epel-release \
    && curl -fsSL -o /etc/yum.repos.d/docker-ce.repo https://download.docker.com/linux/centos/docker-ce.repo \
    && microdnf install -y \
    python3 \
    # python3-pip \
    # libffi-devel \
    # openssl-devel \
    # git \
    docker-ce-cli \
    && python3 -m venv /opt/ansible_venv \
    && . /opt/ansible_venv/bin/activate \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir ansible \
    && rm -rf /opt/ansible_venv/lib/python*/site-packages/ansible_collections/* \
    && ansible-galaxy collection install --upgrade -f \
    ansible.utils \
    ansible.windows \
    community.docker \
    community.general \
    community.hashi_vault \
    community.mysql \
    community.postgresql \
    community.rabbitmq \
    community.windows \
    kubernetes.core \
    microsoft.ad \
    && microdnf clean all \
    && rm -rf /var/cache/* /tmp/* /var/tmp/* /root/.cache /root/.ansible/* rm -rf /var/lib/dnf /var/lib/rpm

ENTRYPOINT ["ansible-playbook"]
CMD ["--version"]

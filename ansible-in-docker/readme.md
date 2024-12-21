# Ansible Docker Image

## Описание

Этот Dockerfile создает образ на основе Rocky Linux 9 minimal, который включает в себя Ansible и ряд полезных коллекций Ansible. Образ оптимизирован для запуска Ansible playbooks в контейнеризированной среде.

## Как запускать

1. Соберите образ:

```
docker build -t ansible-runner .
```
2. Запустите контейнер:

```
docker run --rm ansible-runner
```
По умолчанию это выведет версию Ansible.

3. Для запуска конкретного playbook:

```
docker run --rm -v /path/to/your/playbooks:/playbooks ansible-runner /playbooks/your-playbook.yml
```

## Возможности

- Основан на Rocky Linux 9 minimal для минимального размера образа
- Включает Python 3 и виртуальное окружение для Ansible
- Предустановлен Docker CLI для взаимодействия с Docker из playbooks
- Включает следующие коллекции Ansible:
- ansible.utils
- ansible.windows
- community.docker
- community.general
- community.hashi_vault
- community.mysql
- community.postgresql
- community.rabbitmq
- community.windows
- kubernetes.core
- microsoft.ad

## Дополнительная информация

- Образ использует ENTRYPOINT "ansible-playbook", что позволяет легко запускать playbooks
- Переменные окружения настроены для оптимальной работы Ansible
- Образ очищен от кэшей и временных файлов для уменьшения размера


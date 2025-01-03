# Набор ролей и плейбуков для обслуживания рабочих процессов

## Краткое описание:
Плейбуки:
- `playbooks/new_server/01-preparation.yml`  - первичная подготовка ВМ для получения доступа.

## Пример запуска:

```
ansible-playbook playbooks/"$ИМЯПЛЕЙБУКА"  -i ./inventories/dev/hosts -l hostname -u appsrv
```

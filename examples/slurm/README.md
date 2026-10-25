# Задачи Slurm

Шаги [полного запуска](../../docs/pipeline.md) в виде задач Slurm. Номер файла — номер шага
в `pipeline.md`.

## Переменные

Пути задаются переменными окружения, `sbatch` передаёт их в задачу. Без нужной переменной
задача сразу останавливается.

| Переменная | Что это | Нужна шагам |
|---|---|---|
| `RAW` | папка с `3D-FRONT.zip` и `3D-FRONT-texture.zip` | 1, 4 |
| `SCENES` | распакованные комнаты `3D-FRONT-SCENE` | 1–4 |
| `ROOMS` | список комнат `valid_room_ids.json` | 1, 2 |
| `METADATA` | `source_metadata.json`, результат шага 1 | 1, 2, 4, 8 |
| `SPLITS` | папка разбиения, результат шага 2 | 2, 3 |
| `EXP` | папка эксперимента | 3–6, 8, 10–12 |
| `ARCH` | архитектура комнат, результат шага 4 | 4–6 |
| `SHARE` | папка выгрузки для передачи | 10–12 |

Команда `front3d-pano` должна быть видна в задаче: активируйте окружение, где установлен
пакет, до `sbatch`. Для шагов 5 и 6 это окружение с BlenderProc (`pip install -e .[render]`),
там же задаются `BLENDER_INSTALL_PATH` и `BLENDERPROC_BIN`, если Blender уже стоит.

## Порядок

```bash
export RAW=/data/raw SCENES=/data/3D-FRONT-SCENE ROOMS=/data/3D-Front/valid_room_ids.json
export METADATA=/data/source_metadata.json SPLITS=/data/front3d-split EXP=/data/front3d
export ARCH=/data/front3d-architecture SHARE=/data/front3d-share
mkdir -p logs

sbatch --wait 01_metadata.sbatch
sbatch --wait 02_freeze.sbatch
sbatch --wait 03_init.sbatch
cat "$SPLITS"/{train,val,test}.txt > "$EXP/state/rooms-all.txt"
sbatch --wait 04_architecture.sbatch
sbatch --wait 05_plan.sbatch
sbatch --wait 06_render.sbatch
```

Шаг 7 (`reject`) короткий и требует решения человека: какие комнаты исключить и почему.
Он выполняется вручную по `pipeline.md`, а изменённое разбиение сохраняется.

```bash
sbatch --wait 08_export.sbatch
sbatch --wait 10_images.sbatch
sbatch --wait 11_publish.sbatch
sbatch 12_publish_merge.sbatch
```

`08_export.sbatch` прогоняет этапы разметки по порядку и в конце запускает `validate`.

## Что подстроить под свой кластер

- Раздел (`--partition`) и учётную запись (`--account`) в файлах не указаны.
- Шардированные шаги делятся по `--array`: число шардов равно числу задач массива, менять
  его можно без правки остального.
- Шаги 5 и 6 видеокарту не запрашивают. Если кластер выдаёт GPU только по запросу, добавьте
  `#SBATCH --gres=gpu:1`.
- Если Blender не стартует из-за отсутствующих системных библиотек (`libXi`, `libSM`,
  `libICE`), положите их в отдельную папку и добавьте её в `LD_LIBRARY_PATH` до `sbatch`.

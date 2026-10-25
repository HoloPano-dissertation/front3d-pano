# Полный запуск

Ниже набор собирается с нуля. В примерах исходники лежат в `/data/raw` (архивы 3D-FRONT)
и `/data/3D-FRONT-SCENE` (распакованные комнаты GLB), эксперимент — в `/data/front3d`.
Что скачать, описано в [data_sources.md](data_sources.md).
Те же шаги в виде задач Slurm лежат в [examples/slurm/](../examples/slurm/README.md).

| Шаг | Нужно | Время (ориентир) |
|---|---|---|
| 1–3, 5 | процессор | минуты; `freeze` на ~10 тыс. комнат — около 15 минут |
| 4 | процессор | часы, шардируется |
| 6–7 | GPU, Blender | около часа на 1000 комнат на одной A100, шардируется |
| 8–9 | процессор | часы, шардируется по этапам |

## 1. Масштабы и классы из исходного релиза

```bash
front3d-pano metadata /data/raw/3D-FRONT.zip /data/3D-FRONT-SCENE \
  /data/source_metadata.json --rooms /data/3D-Front/valid_room_ids.json
```

Для каждой комнаты считается точный множитель «метров на единицу» и класс каждого
предмета, как — в [metric_scale.md](metric_scale.md). Файл `source_metadata.json` дальше
передаётся в `freeze` и `export`.

## 2. Состав набора

```bash
front3d-pano freeze /data/3D-FRONT-SCENE --splits /data/front3d-split \
  --metadata /data/source_metadata.json --rooms /data/3D-Front/valid_room_ids.json
```

Каждая комната проходит четыре проверки по порядку: восстанавливается ли контур, правдоподобен
ли масштаб, сходится ли мебель на одном масштабе, можно ли поставить четыре камеры. Первая
непройденная проверка исключает комнату, причина записывается. Оставшиеся комнаты делятся
на части по домам: все комнаты одной квартиры попадают в одну часть (по умолчанию
70 / 15 / 15 %; `--val`, `--test`, `--seed`).

Результат пишется в папку `--splits`: `train.txt`, `val.txt`, `test.txt` и
`excluded_rooms.json` с причинами. Эта папка и есть состав набора: её хранят вместе
с результатами и передают тем, кто собирает тот же набор. Существующее разбиение без `--force` не перезаписывается:
прежние числа иначе относились бы к другому набору.

Камеры здесь проверяются без Blender, по точкам с треугольников сетки. Полного совпадения
с рендерером нет, поэтому окончательная проверка — шаг 5.

## 3. Эксперимент

```bash
front3d-pano init /data/3D-FRONT-SCENE /data/front3d --splits /data/front3d-split
```

Папки `/data/front3d` ещё не должно быть. `init` заново восстанавливает контур каждой
комнаты, копирует разбиение в `splits/` эксперимента и пишет `splits/rooms.jsonl` —
список комнат для рендера.

## 4. Архитектура комнат

```bash
cat /data/front3d-split/{train,val,test}.txt > /data/front3d/state/rooms-all.txt
front3d-pano architecture /data/raw/3D-FRONT.zip /data/raw/3D-FRONT-texture.zip \
  /data/3D-FRONT-SCENE - /data/front3d-architecture \
  --rooms /data/front3d/state/rooms-all.txt --metadata /data/source_metadata.json
```

Стены, полы, потолки, плинтусы, откосы и встроенные шкафы собираются из исходного релиза
вместе с материалами и совмещаются с мебелью переработки. Результат —
`<папка>/<дом>/<комната>/architecture.obj` и общая папка текстур. Шардируется ключами
`--shard-count N --shard-index I`.

## 5. План камер

```bash
front3d-pano render /data/front3d/splits/rooms.jsonl /data/front3d/plan \
  --views 4 --plan-only --architecture-root /data/front3d-architecture
```

Всё, что делает рендер, кроме самой отрисовки: камеры выбираются, `render.json` пишется,
HDF5 нет. План должен пройти без отказов. Комнаты, где камеру поставить негде, видны
здесь заранее.

## 6. Рендер

```bash
front3d-pano render /data/front3d/splits/rooms.jsonl /data/front3d/outputs \
  --views 4 --samples 96 --architecture-root /data/front3d-architecture \
  --ambient 4.0 --light-temperature 2700-5000
```

Результат — `outputs/<часть>/<дом>/<комната>/{0..3}.hdf5`, `render.json` и метка
`.complete`. Шарды: `--shard-count N --shard-index I`, каждый шард — отдельный процесс,
хоть на разных машинах. Отказ по комнате не останавливает шард: он попадает
в `outputs/shard-NNN.json` вместе с текстом ошибки рендерера, а код выхода будет 2.

**Возобновление.** Повторный запуск в ту же папку пропускает комнату, только если метка,
метаданные и все кадры на месте, а код рендерера и параметры совпадают. Комната без метки,
с пустым кадром или с остатками прерванного запуска рисуется заново. Если изменился код
рендерера (`render.json` хранит хеши его файлов), запуск останавливается: рендеры разного
кода в одной папке не смешиваются. После изменения исходных GLB или архитектуры тоже нужна
новая папка: хеши проверяют только код.

Переменные окружения: `BLENDER_INSTALL_PATH` — готовый Blender вместо скачивания,
`BLENDERPROC_BIN` — нестандартный путь к `blenderproc`, `BLENDERPROC_TEMP_DIR` — папка
временных файлов.

## 7. Комнаты, которые не отрисовались

Рендерер работает с настоящими сетками и может отвергнуть комнату, которую `freeze`
пропустил. Такие комнаты переводятся в исключения, и у каждой должна быть причина:

```bash
python - <<'EOF'
import glob, json
reasons = {}
for path in glob.glob("/data/front3d/outputs/shard-*.json"):
    for row in json.load(open(path))["failed"]:
        reasons[row["room_id"]] = row["reason"] or "exit code %d" % row["exit_code"]
json.dump(reasons, open("/data/front3d/state/render-failure-reasons.json", "w"), indent=2)
EOF

mkdir -p /data/front3d/rendered
for part in train val test; do
  for house in /data/front3d/outputs/$part/*/; do ln -s "$house" /data/front3d/rendered/; done
done

front3d-pano reject /data/front3d --splits /data/front3d-split \
  --rendered /data/front3d/rendered \
  --reasons /data/front3d/state/render-failure-reasons.json
```

`--rendered` ждёт комнаты в виде `<дом>/<комната>/`, без уровня части набора, поэтому выше
собирается папка ссылок. Комнату без причины исключить нельзя: команда остановится и
перечислит такие комнаты. Исключить комнаты поимённо:
`front3d-pano reject /data/front3d --splits /data/front3d-split --rooms list.txt --reason "почему"`.

`reject` правит разбиение в папке `--splits` и состав эксперимента. Изменённое
разбиение нужно сохранить: по нему другие соберут тот же набор.

## 8. Разметка

```bash
front3d-pano export /data/front3d \
  --scale-table /data/source_metadata.json --class-table /data/source_metadata.json
```

Этапы по порядку: `rgb → ground_truth → relations → shape → coco`. Один этап —
`--stage <имя>`. Каждый этап — отдельный процесс.

Порядок важен: `relations` и `shape` дописывают файлы эталона. Если перезапустить
`ground_truth` отдельно, отношения и пути к сеткам пропадут, и эти этапы, а также всё,
что от них зависит, нужно прогнать снова. Готовые PNG и ссылки переиспользуются, поэтому
при смене исходников или рендера нужна новая папка эксперимента.

Комнаты с неправдоподобным масштабом останавливают `export`; `--allow-unscalable` только
записывает их.

Формат каждого результата — [output_format.md](output_format.md).

## 9. Проверка

```bash
front3d-pano validate /data/front3d
```

`validate` сверяет выгрузки между собой: состав частей набора, совпадение идентификаторов
видов, размеры панорам, рамки эталона, маски и классы COCO. Это проверка форматов, а не
одобрение качества: перед обучением набор нужно посмотреть глазами.

## Выгрузка для передачи

```bash
for split in train val test; do
  front3d-pano images /data/front3d/outputs/$split /data/front3d-share/panoramas/png
done
front3d-pano publish /data/front3d /data/front3d-share
front3d-pano publish /data/front3d /data/front3d-share --merge
```

Собирает набор в том виде, в каком им делятся: панорамы, разметку и README. Перед
передачей стоит перечитать условия использования в [data_sources.md](data_sources.md).

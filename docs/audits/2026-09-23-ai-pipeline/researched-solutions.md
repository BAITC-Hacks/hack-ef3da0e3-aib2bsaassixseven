# AI pipeline: researched solutions

Дата исследования: 2026-09-23. Роль: второй агент engineering loop. Это план, production-код не менялся. Изучены `backend/ML_README.md`, `backend/ml_pipeline/*.py`, доступная память Octarin и первичные источники ниже. GPU/Brev измерения выполняет основной агент; здесь нет собственного GPU benchmark. Незакоммиченный код рассматривается как фактическая рабочая версия.

## Вывод

Первый приоритет — исправить логику сохранения поручений, оснований и дат, затем измерить весь pipeline на размеченных совещаниях. Замена модели сама по себе не исправит неверную отмену задачи, потерю года или принятие цитаты за доказательство назначения. Текущие GigaAM Large + Community-1 + Qwen3.5-9B — разумный baseline для сравнения, но не доказанный победитель.

Inference остается на NVIDIA/customer server. Скачать публичные веса в отдельной стадии подготовки допустимо; аудио и транскрипты не отправляются внешним AI API. Общая память про cloud baseline относится к другому проекту и здесь не применяется.

### Проверенное окружение Brev

Основной агент 2026-09-23 проверил доступный Jupyter и live environment: NVIDIA L40S, 46 068 MiB device memory, driver 565.57.01. В момент снимка занято 21 657 MiB, GPU utilization 97%; это моментальная загрузка, не peak memory или benchmark pipeline. `/data`: 251G total, 32G used, 208G available. SHA всех 11 Python-файлов `ml_pipeline`, `pyproject.toml` и `uv.lock` совпали между remote и local на момент проверки.

Подготовлены `diarization`, `gigaam-ctc`, `gigaam-large-ctc`, `rukk`, `whisper-turbo`, `qwen3.5-9b`. `qwen3-4b` и `issai-4b-kazakh` пока не подготовлены: их сравнение требует отдельной загрузки до offline inference. Другой task уже выполняет корректирующий процесс; эти сведения не означают, что его изменения или результаты проверены данным исследованием. Повторно сверять code/config hashes перед следующим benchmark. Аудит не вмешивался в работающий процесс.

## Что действительно подтверждают источники

| Компонент | Подтверждение | Применение и ограничение |
|---|---|---|
| GigaAM Multilingual | Варианты CTC 220M и Large CTC 600M; русский и казахский; документированный `AutoModel` + `transcribe`. Публичная оценка исключает записи длиннее 30 s и references с цифрами. [S1] | Сохранить Large как baseline, сравнить small на тех же данных. Опубликованные WER не доказывают точность чисел, имен, наложений и переключения языков на пользовательских встречах. |
| Rukk | Авторский пример использует ровно текущую схему TorchScript, `logits[0].argmax(-1)` и blank=`max(tokens)+1`; mixed имеет отдельную модель. [S2] | Не объявлять decoder сломанным без воспроизведения. Сначала GPU smoke и проверка пустого/короткого/обычного audio; затем benchmark смешанной речи. KenLM — отдельный эксперимент, преимущество на monolingual kk нельзя переносить на rukk. |
| Community-1 | Поддерживает локальный offline запуск, waveform 16 kHz, regular и exclusive outputs, ограничения числа говорящих. [S3] | Сохранить. Exclusive пригоден для простого назначения speaker, но сохранить также regular output для overlap и DER. Знать число приглашенных — не значит знать число говоривших. Hosted Precision-2 не входит в этот local-only план. |
| Qwen3.5-9B | Документированы мультимодальная загрузка, отключение thinking и text-only serving. [S4] | Текущая multimodal загрузка не является сама по себе багом. Text-only serving — возможная оптимизация после проверки pinned версии. General benchmarks не заменяют измерение extraction ru/kk. |
| Qwen3-4B-Instruct-2507 | Это фактическая модель alias `qwen3-4b` в catalog; поддерживает только non-thinking. [S5] | Отсутствие `enable_thinking=False` в этой ветке не баг. Полезный меньший baseline; не подменять его исходным Qwen3-4B. |
| ISSAI Qwen3.5-4B-Kazakh | Расширен казахский tokenizer; continued pretraining + chat-vector merge. Оценка карточки проведена с thinking. [S6] | Кандидат для kk; качество non-thinking строгого JSON в текущем pipeline нужно измерить отдельно. Улучшение KazMMLU не доказывает качество поручений. |

## Исправления по корневым причинам

### Этап 1: исправления семантики в текущей архитектуре

Findings первого агента подтверждены его CPU probes. Третий агент независимо воспроизвел четыре ошибки (год, отрицание даты, отмена чужой задачи, resurrection), несмотря на 71 проходящий существующий тест. Это дефекты кода, а не оценки качества конкретной модели.

1. **Salvage не должен возвращать удаленный пункт.** Сейчас повторная валидация `single` может удалить задачу, после чего salvage добавляет исходный `item`. Сделать валидацию возвращающей новый validated result, либо брать только реально оставшиеся элементы `single`. Убрать скрытое смешение проверки, дополнения и удаления. Gate: отмененная task не воскресает при третьей неуспешной попытке grounding; хороший соседний пункт сохраняется.
2. **Отмена и назначение требуют связи с конкретной задачей.** Совпадение одного stem «договор» не разрешает удалить договор поставки из-за отмены договора аренды. Имя в четырех предыдущих turns не доказывает владельца новой темы. Минимальная мера: сомнительное событие сохранять на review, не менять активную задачу и не повышать имя до подтвержденного owner. Gate: одноименные объекты, смена темы, два человека, «не отменяем», обсуждение будущей отмены, подтвержденная отмена и повторное поручение.
3. **Даты: explicit year и negation до коротких regex.** «До 2 октября 2027 года» не должно превращаться в 2026-10-02; «не завтра, а через три дня» не должно давать завтра. Вернуть `due_text`, nullable date и reason (`ambiguous`, `unsupported`, `missing_anchor`, `conflicting`) при неоднозначности. Не навязывать дату только потому, что парсер нашел знакомый фрагмент. Gate: ru/kk, explicit year без meeting_at, отрицание, альтернативы, диапазоны, смена года, timezone, отсутствующая дата встречи. Поддержка natural language date library допускается только после этих же regression fixtures; замена библиотеки сама по себе не gate.
4. **Никакой потери транскрипта при падении LLM.** Сохранять completed stage artifacts до следующей стадии, с run manifest (`running/completed/failed`, last completed stage), атомарным завершением и причинами ошибок. Resume должен проверять hashes/version/config. Gate: kill/invalid JSON после ASR сохраняет transcript; перезапуск не повторяет ASR; частичный результат не выдается за завершенный.

### Этап 2: управляемые изменения состояния и grounding

После исправлений этапа 1 ввести небольшую явную модель событий поручения, без нового vector DB или сложного agent framework. Номера этапов обозначают порядок выполнения, а не severity дефектов:

- `task_id`, `event_id`, `operation=create/update/cancel/reinstate`, `target_task_id`, ordered source references; исходное событие неизменно. IDs назначает приложение; выбранный LLM target остается гипотезой до проверки связи, наличие ID само по себе ничего не доказывает.
- Отдельные evidence spans для action, owner, deadline и cancellation: `utterance_id`, start/end character offsets, exact text. Разрешены несколько оснований, в том числе вопрос + ответ.
- LLM предлагает событие и связь; deterministic reducer применяет только валидные переходы. Неоднозначные targets не меняют состояние автоматически. Повторный event идемпотентен. Удаление из итогового списка не уничтожает audit history.
- `needs_review` остается пользовательским сигналом, дополненным конкретной причиной. Literal substring проверяет наличие цитаты; она не доказывает, что указанное лицо действительно получило это действие. Проверять citation coverage и semantic support отдельно. ALCE разделяет correctness и citation quality; это методологическая опора, а не готовый ru/kk judge. [S10]

Цена: migration схемы и разметка event fixtures. Более дешевый промежуточный вариант — stable IDs и update proposals поверх существующего JSON. Полный свободный LLM rewrite списка проще, но сохраняет риск тихих удалений и нестабильного связывания. Автоматический NLI/LLM judge может сортировать review, но его нельзя считать независимым oracle без ru/kk validation.

Gate: same final state при изменении размеров chunk с неизменной хронологией; задача не исчезает без подтвержденного explicit cancel event; неоднозначные/противоречащие events сохраняются на review; позднее подтвержденное reinstatement имеет явный приоритет; все подтвержденные cancellations/updates имеют адресата и evidence; adversarial transcript instructions остаются данными; владелец/дата не берутся просто из списка участников. Event log дает аудит и детерминированное применение, но сам не решает entity resolution — это отдельный gate. Независимый верификатор поддержал направление именно с постепенным внедрением после этапа 1.

### Этап 2: ограничить фактический prompt и сохранить границы evidence

`chunk_chars` ограничивает лишь новые utterances; старое state и reconciliation context растут отдельно. Считать tokenizer tokens полного chat template + sources + state + output reserve. Задать явный measured context budget и timeout/retry budget. Не молча обрезать прошлое: хранить events снаружи prompt, включать ограниченный набор соответствующих task sources и окно соседних turns. Если зависимость не помещается, разделить запрос или отправить событие на review.

При разделении одной utterance fragment должен иметь уникальный fragment ID и ссылку на original ID+offsets: повторяющийся ID нельзя сворачивать в dict с последним куском. Gate: длинная utterance с evidence в первом фрагменте, 50+ chunks с переносом срока в конце, большой JSON, context exhaustion и output truncation. Полный state не должен исчезать из-за partial salvage.

## Benchmark, который позволит выбрать модели

Основной агент сверил приложенный ZIP: аудио hashes совпадают с MP3, в архивном output 18 задач, 8 без владельца, все 18 без даты, все 45 пунктов требуют review. Отсутствие `meeting_at` объясняет невозможность вычислить относительные даты; это не автоматически 18 ошибок. Архивное назначение отчета в M2 и потеря сметы показывают необходимость field-level evidence и диалогового адресата; текущая рабочая версия могла уже исправить часть архивных проблем. Проверять их на current code перед объявлением незакрытым дефектом. Следующее имя при переходе повестки не является владельцем предыдущего поручения. Протоколы имеют расхождения с аудио и не принимаются за gold без прослушивания.

1. Зафиксировать audio hash, модельные SHA, code snapshot hash (включая dirty diff), uv lock hash, prompts/schema, config, hardware/runtime и нормализацию текста. Текущий model lock полезен, но не описывает все условия эксперимента.
2. Вручную разметить оба доступных совещания: ru/kk/mixed интервалы, слова/имена/числа, говорящих и overlap, конечные поручения и события отмены/переноса. Протокол — образец желаемого результата, но не автоматически точный transcript gold. Не использовать уже подогнанные встречи как доказательство обобщения: следующий набор встреч держать отдельно; при двух встречах говорить о regression coverage, не о production accuracy.
3. Оставить oracle-segment WER/CER как изолированную ASR метрику. Добавить end-to-end scoring полного transcript, VAD speech loss, regular diarization DER с объявленной overlap/collar политикой; при speaker gold — cpWER/tcpWER. MeetEval предоставляет такие метрики и форматы. [S9] Без speaker/time labels эти метрики честно остаются unavailable.
4. Отдельно оценивать extraction на gold transcript и на каждом ASR transcript. Измерять task precision/recall, owner/date correctness, cancellation survival, missed updates, unsupported field rate, citation coverage и долю review. Иначе невозможно отличить проблему ASR от reasoning.
5. Заменить greedy `SequenceMatcher>=0.55` как главный gate на согласованные human task links или стабильные gold task/event IDs. Bipartite matching может убрать зависимость от порядка, но само по себе не дает semantic truth. Не считать `due_date=null` успехом, если система потеряла требуемое due_text.
6. Кэшировать decode/VAD/diarization один раз, ASR один раз на модель+audio+segmentation hash, extraction отдельно по LLM. Существующий compare повторяет full speech pipeline для каждой пары. После отбора выполнить хотя бы один fresh end-to-end run выбранной комбинации, чтобы cache не скрывал integration failures.

Предлагаемый первый раунд: GigaAM Large vs small vs Rukk vs Whisper Turbo на speech dataset; Qwen3.5-9B vs Qwen3-4B-Instruct-2507 vs ISSAI на одинаковом gold transcript. Затем проверить 1–2 лучших пары end-to-end. «Лучший» выбирается по task correctness с соблюдением budget, а не только WER или общей LLM leaderboard. Численные quality thresholds должны быть утверждены относительно размеченного baseline; сейчас они не измерены. Обязательные инварианты (даты, evidence, отсутствие resurrection) должны проходить на всех regression cases.

## Локальная производительность: сначала измерить, затем менять engine

Собрать cold/warm stage wall time, audio duration, RTF, LLM input/output tokens, retries, peak allocated/reserved CUDA memory и process GPU memory, CPU RAM, failures. Mean/p95 имеет смысл лишь при объявленном числе измерений. Цена = фактическая оплачиваемая длительность × тариф пользователя; тариф и run time здесь неизвестны.

Оставить sequential loading как baseline. Затем пробовать batch ASR с ограничением total audio samples, только если API pinned модели поддерживает это; тестировать equivalent texts и timestamps. Faster-whisper документирует batching, CUDA/cuDNN требования и speed/memory tradeoff, но его числа на RTX 3070 Ti нельзя объявлять latency L40S. [S7]

Если JSON retries или throughput LLM являются измеренным bottleneck, отдельный pinned local vLLM environment с JSON Schema decoding и text-only Qwen serving — кандидат. vLLM поддерживает schema из Pydantic [S8], но schema не доказывает смысл и не предотвращает max-token truncation. Избежать непроверенного upgrade Torch в едином speech environment; запускать сервис только на customer host, явно задавать local base URL, context budget и memory budget. Для одного последовательного batch job простые Transformers могут быть достаточны.

4/8-bit quantization — только следующий A/B эксперимент; уменьшение памяти и возможное ускорение не равны сохранению owner/date accuracy. Общая документация описывает quantization и аппаратные требования [S12], но не дает измерений именно этого pipeline. Параметрическое умножение числа weights на 2 байта — нижняя оценка weights, не VRAM requirements: еще нужны KV cache, activations, allocator и runtime. Здесь не обещается ни fit, ни определенный RTF.

Не делать автоматический переход на WhisperX как «исправление всего»: forced alignment требует подходящей языковой модели; project docs отдельно предупреждают про overlap и невыравниваемые символы [S11]. Сначала проверить ru/kk/code-switch alignment и coverage чисел на отдельной ветке. Сохранение original timestamps и повторяемой segmentation уже важнее непроверенной миграции.

## Первичные источники

Все URL проверены 2026-09-23. Model cards/docs изменяемы; перед внедрением зафиксировать конкретные revisions. Приведенные источники использовались для чтения, пользовательское содержимое им не передавалось.

- **S1:** [ai-sage GigaAM Multilingual model card](https://huggingface.co/ai-sage/GigaAM-Multilingual). Семейство/варианты, API, протокол WER. Статья указана авторами как arXiv 2607.10371, 2026.
- **S2:** [Rukk author model card (raw)](https://huggingface.co/alibiserikbay/kazakh-russian-mixed-stt/raw/main/README.md). TorchScript/CTC contract и результаты; это авторские измерения, не независимый meeting benchmark.
- **S3:** [pyannote Community-1 model card](https://huggingface.co/pyannote/speaker-diarization-community-1). Offline, exclusive/regular diarization, speaker bounds; таблица benchmark датирована авторами 2025-09.
- **S4:** [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B). Chat template/mode и text-only serving; runtime support проверять на pinned build.
- **S5:** [Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507). Non-thinking-only contract.
- **S6:** [ISSAI Qwen3.5-4B-Kazakh model card](https://huggingface.co/issai/Qwen3.5-4B-Kazakh). Метод адаптации и условия evaluation.
- **S7:** [SYSTRAN faster-whisper](https://github.com/SYSTRAN/faster-whisper). Batching, native dependencies, условия опубликованных benchmark.
- **S8:** [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/). JSON Schema/Pydantic local inference.
- **S9:** [MeetEval](https://github.com/fgnt/meeteval). Meeting transcription metrics и reference formats.
- **S10:** [Gao et al., Enabling Large Language Models to Generate Text with Citations, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.398/). Разделение correctness и citation evaluation, опубликовано December 2023.
- **S11:** [WhisperX](https://github.com/m-bain/whisperX). Language-specific alignment и ограничения.
- **S12:** [Transformers bitsandbytes quantization](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes). Форматы и аппаратные зависимости.

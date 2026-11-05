# Cambios para el informe (Overleaf) — 5-nov-2026

Para Juan Diego. Texto **en inglés**, listo para pegar en `main.tex` de Overleaf. Cada bloque dice la **sección**, la
frase **que se reemplaza** (tal como está hoy en `report/main.tex`) y la **nueva**. Lo que todavía no está medido va
como `\pendiente{...}` (sale en rojo): no se reemplaza por números sintéticos. El paquete `informe_overleaf.zip` (carpeta
`para_anzola`) trae el `main.tex` actual, la bibliografía y las figuras.

---

## 1. Abstract

**Reemplaza:**
> `a VL53L0X laser range sensor, BME280 and BH1750 environmental sensors, a GPS receiver and a microSD logger;`

**Por:**
> `a VL53L0X laser range sensor, DHT22 and BH1750 environmental sensors, a GPS receiver and a microSD logger;`

**Reemplaza:**
> `... and a MobileNetV3 classifier exported to TensorFlow Lite int8 and evaluated with a site-grouped split.`

**Por:**
> `... and a convolutional classifier exported to TensorFlow Lite int8 with quantization-aware training, evaluated with a site-grouped split, explained with Grad-CAM and executed offline in the phone's web browser.`

## 2. System Overview (después de "…the node gained environmental sensors to annotate those photos.")

**Agregar:**
> `The municipality of Tunja has verbally supported pilot tests on city streets; a formal USTA--municipality agreement and the answers to our information requests are in progress (\pendiente{status of the agreement and of the municipal data at delivery}).`

## 3. Data Acquisition — Sensors and Sampling

**Reemplaza:**
> `A BME280 (temperature, humidity and pressure; a DHT22 replaces it if only a BMP280 is available) and a BH1750 light sensor are read every 10~s and logged with GPS time to annotate the photo dataset.`

**Por:**
> `A DHT22 (temperature and relative humidity, one-wire) and a BH1750 light sensor are read every 10~s and logged with GPS time to annotate the photo dataset; the driver also accepts a BME280 and detects BMP280 clones without a humidity channel.`

**Reemplaza:**
> `The first datasets were recorded with a phone (phyphox \cite{staacks2018phyphox}: accelerometer with gravity, gyroscope and GPS) at up to 30~km/h, following a written protocol (fixed mount, co-driver labeling);`

**Por:**
> `The first datasets were recorded with an iPhone running phyphox \cite{staacks2018phyphox} (accelerometer with gravity, gyroscope and GPS; about 100~Hz, the maximum rate available on iOS) at up to 30~km/h, following a written protocol: fixed mount, one minute standing still at the start and at the end, and co-driver labeling with the phone's stopwatch started together with phyphox. Each lap press marks an event; since iOS shows the duration of each lap rather than the cumulative time, a script adds the durations to obtain event times, and "stop" laps mark intervals in which the car is standing and the detector is disabled. A field validator checks every export (sampling rate, gaps, GPS coverage, still periods) before processing;`

## 4. Computer Architecture — Buses and Pins

**Reemplaza:**
> `The MPU-6050, VL53L0X, BME280 and BH1750 share I\textsuperscript{2}C at 400~kHz (the slow environmental sensors are read in the same task, so no bus lock is needed) and the GPS uses UART2. Removing the camera freed GPIO~25 and~35; GPIO~25 hosts the optional DHT22 one-wire line.`

**Por:**
> `The MPU-6050, VL53L0X and BH1750 share I\textsuperscript{2}C at 400~kHz (the slow environmental sensors are read in the same task, so no bus lock is needed) and the GPS uses UART2. Removing the camera freed GPIO~25 and~35; GPIO~25 hosts the DHT22 one-wire line.`

## 5. Computer Architecture — FIFO, Interrupt and DMA Ping-Pong (agregar al final del párrafo)

> `The node's web page, served from core~0, plots the vertical acceleration live (a 20~Hz decimated buffer shared through a spinlock), lets the co-driver tune the detector thresholds, which are stored in non-volatile storage and applied between blocks, and downloads the session files over Wi-Fi without removing the card; all card accesses share one mutex. A 10~s task watchdog, automatic restart of the GPS UART when no NMEA bytes arrive, card remounting after a failed write, per-session numbering kept in flash and a status LED make the node usable in the field; at most about 1~s of data is lost on a power cut. \pendiente{validated on the board}.`

## 6. Image Dataset and Classifier

### 6.1 Collection Protocol — reemplaza "Collected so far: \pendiente{photos, sites and photos per class}."

> `Photos are taken with an iPhone 15 (JPEG or HEIC, location enabled) and each site is recorded in a shared field sheet (time, class, severity, surface, wet surface, light, weather, location). The ingestion joins each sheet row to the photos taken within 5~min and to all photos of the same site; the road class comes automatically from the OpenStreetMap segment and the surface (asphalt, concrete, pavers, unpaved) from the sheet. Collected so far: \pendiente{photos, sites and photos per class}.`

### 6.2 Nueva subsección antes de "Classifier": External Datasets

> `\subsection{External Datasets}`
> `Two public pothole datasets were reviewed before use. The Kaggle "Pothole Detection" set (665 images with PASCAL VOC boxes, Database Contents License v1.0, originally from MakeML) can be used for academic work with attribution and serves as an auxiliary pothole/no-pothole pre-training task built from crops inside and outside the boxes. A Hugging Face mirror with 4\,719 images was discarded: its image license is undocumented, it mixes real and synthetic images of untraceable origin, and its own card reports near-duplicates between train and test. External images never enter the evaluation, which always uses our photos split by site. \pendiente{whether pre-training was used and its effect on macro-F1}.`

### 6.3 Classifier — reemplaza el párrafo completo que empieza "A MobileNetV3-Small \cite{howard2019mobilenetv3} pretrained…"

> `Two ImageNet-pretrained backbones are fine-tuned on \(224\times224\) inputs: MobileNetV3-Small \cite{howard2019mobilenetv3} and MobileNetV2 \cite{sandler2018mobilenetv2}. Training uses class weights and augmentations designed for Tunja: night (dark, bluish, sensor noise), wet pavement (darker, desaturated, specular reflections), hard shadows, slight blur, small rotations and perspective changes. Train, validation and test sets are split \emph{by site} with stratified group folds: all photos of the same spot (within 15~m) fall on the same side, because a per-photo split would let the model recognize places instead of classes. Each model is exported to TensorFlow Lite in float32, with full-integer int8 post-training quantization (PTQ) calibrated on 200 training photos or on 1\,000 augmented samples, and, for MobileNetV2, with quantization-aware training (QAT) \cite{jacob2018quant}; MobileNetV3's hard-swish blocks are not supported by the QAT toolkit. Accuracy, macro-F1, size and latency are compared for every variant on the same test set, and Grad-CAM \cite{selvaraju2017gradcam} shows which regions drive each prediction. The whole pipeline was verified end to end with synthetic images, which are flagged and never reported as results. Results: \pendiente{per-class precision, recall and F1, confusion matrix, and accuracy/macro-F1/size/latency for float32, int8 PTQ and int8 QAT}.`

### 6.4 Nueva subsección: On-Phone Inference and Citizen Channel

> `\subsection{On-Phone Inference}`
> `The selected int8 model runs inside the phone's web browser with TensorFlow Lite compiled to WebAssembly: the page is served once from the laptop over local Wi-Fi and then works offline; the photo never leaves the phone, and the page shows the class, the confidence and the measured latency (\pendiente{latency on the iPhone 15}). The same model suggests a class for every photo received by the Telegram bot (``looks like a pothole, 87\,\%''); the suggestion is stored with the report and its model version but does not replace human review, and the bot states it when the model was trained on synthetic data.`

## 7. Data Structures (después de "...connected components of high-risk segments (candidate work orders).")

> `A second view lists citizen reports and node events ordered with the same binary max-heap by priority = severity \(\times\) traffic \(\times\) recurrence, where severity is normalized to 1--3, traffic weights the OpenStreetMap road class (1--3) and recurrence counts open hazards on the same segment with the hash table; building the priorities and the heap costs \(O(n)\) and extracting the top \(k\) costs \(O(k\log n)\).`

## 8. Results Summary — tabla `tab:metrics` (reemplazar la fila del clasificador por estas)

> `Photo classifier macro-F1, float32 / int8 PTQ / int8 QAT (by site) & reported & \pendiente{F1} \\`
> `Photo classifier latency on the iPhone (browser) & reported & \pendiente{ms} \\`

## 9. Discussion and Limitations — futuro (reemplaza la frase "Future work, outside the scope…")

> `Future work, outside the scope of this delivery: a laser grid module (structured light) to measure pothole depth, which could not be obtained in time; an optional read-only OBD-II link (ELM327 over Bluetooth) to use the vehicle speed as a backup for GPS; automatic on-vehicle capture with a camera module, whose firmware is kept in the repository but removed from the design; and a bounding-box detector trained on the external dataset. The municipal pilot will provide independent ground truth once the agreement is formalized.`

## 10. Ethical and Legal Considerations (agregar al final)

> `On-phone classification keeps the photo on the device, and the bot's automatic suggestion is advisory: a person confirms every report.`

## 11. Bibliografía nueva (agregar a `referencias.bib`)

```bibtex
@inproceedings{sandler2018mobilenetv2,
  author={Sandler, Mark and Howard, Andrew and Zhu, Menglong and Zhmoginov, Andrey and Chen, Liang-Chieh},
  title={{MobileNetV2}: Inverted Residuals and Linear Bottlenecks},
  booktitle={Proc. IEEE/CVF Conf. Computer Vision and Pattern Recognition (CVPR)},
  address={Salt Lake City, UT, USA}, pages={4510--4520}, year={2018}
}
@inproceedings{selvaraju2017gradcam,
  author={Selvaraju, Ramprasaath R. and Cogswell, Michael and Das, Abhishek and Vedantam, Ramakrishna and Parikh, Devi and Batra, Dhruv},
  title={{Grad-CAM}: Visual Explanations from Deep Networks via Gradient-Based Localization},
  booktitle={Proc. IEEE Int. Conf. Computer Vision (ICCV)},
  address={Venice, Italy}, pages={618--626}, year={2017}
}
@misc{makeml_potholes,
  author={{Make ML}}, title={Potholes Dataset}, howpublished={\url{https://makeml.app/datasets/potholes}},
  note={Republished as ``Pothole Detection'' on Kaggle (andrewmvd). Database Contents License v1.0}
}
```

(Si se usa el dataset de Kaggle, citar `\cite{makeml_potholes}` en 6.2.)

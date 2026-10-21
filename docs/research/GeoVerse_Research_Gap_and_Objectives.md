# GeoVerse: Research Gap, Aim, and Objectives Alignment Document

**Project Title:** GeoVerse: A Multi-Modal Spatio-Temporal Framework for Urban Growth, Property Value, and Future Accessibility Prediction  
**Authors:** Pranav Vasu, Sanchit Wagh, Uzair Sayyed, Aayush Wakule, Dr. Kaushalya Thopate  
**Institution:** Department of Computer Engineering, Vishwakarma Institute of Technology, Pune, Maharashtra, India  
**Target Venue:** IEEE / Scopus-Indexed Academic Conference / Journal  

---

## 1. Executive Summary and Problem Context

Urban agglomerations in emerging economies—exemplified by the Pune Metropolitan Region in Maharashtra, India—are undergoing rapid, non-linear physical expansion. This growth is accompanied by escalating real estate valuation volatility and complex transportation bottlenecks. Traditionally, urban expansion simulation, real estate econometric modeling, and transportation network routing have been investigated in academic silos:
1. **Remote sensing and urban growth studies** model physical land-use/land-cover (LULC) transitions using cellular automata or spatio-temporal deep learning, largely ignoring microeconomic valuation feedbacks and infrastructure impedance.
2. **Real estate appraisal models** rely on hedonic pricing regression or gradient-boosted decision trees using static transactional features and proximal point-of-interest (POI) counts, neglecting forward-looking physical growth vectors and infrastructure changes.
3. **Transportation accessibility frameworks** compute shortest or fastest paths across static OpenStreetMap (OSM) road topologies, failing to incorporate dynamic development friction or projected urban expansion corridors into future-scenario route costs.

The **GeoVerse** project addresses this fragmentation by proposing an integrated multi-modal spatio-temporal intelligence framework that establishes an explicit, unidirectional information-flow pipeline:
$$\text{Remote Sensing \& Spatial Indicators} \xrightarrow{} \text{Model 1 (Urban Growth)} \xrightarrow{} \begin{cases} \text{Model 2 (Property Valuation)} \\ \text{Model 3 (Future-Aware Routing)} \end{cases}$$

---

## 2. Synthesis of Prior Literature and Specific Research Gaps

A rigorous synthesis of foundational and recent literature reveals four interconnected gaps:

### Gap 1: Disconnection Between Remote Sensing Growth Signals and Economic Valuations
While remote sensing models (e.g., Random Forest Cellular Automata by Yang et al., 2015; ConvLSTM architectures by Shi et al., 2015; and Spatio-Temporal Foundation Models such as UniST by Yuan et al., KDD 2024) provide high-fidelity urban boundary forecasts, econometric property models (e.g., Sharma et al., 2023; Chen et al., 2022) do not consume these dynamic spatial transition probabilities. Consequently, property price forecasting models suffer from "temporal blindness," failing to capture appreciation surges driven by impending peri-urban conversion.

### Gap 2: Inability of Transportation Networks to Anticipate Spatial Urban Growth
Conventional routing systems (e.g., Dijkstra, A*, Contraction Hierarchies) rely on static road networks or historical telemetry. When urban planners simulate future connectivity 5 to 10 years ahead, route planning tools treat the surrounding built environment as invariant. They fail to parameterize how projected development density introduces transit friction, bottlenecks, and modal strain onto existing arterial corridors.

### Gap 3: Absence of Multi-Modal Alignment Protocols for Heterogeneous Geospatial Data
Urban data spans distinct spatial and temporal modalities: satellite multi-spectral rasters (Sentinel-2, 10m/30m grids), demographic grids (WorldPop, 100m cells), vector topologies (OpenStreetMap road graphs and POIs), and discrete irregular property transactions. Prior frameworks either collapse all data into coarse tabular aggregates (losing fine-grained spatial gradients) or focus exclusively on raster grids without graph topological awareness.

### Gap 4: Controlled Evaluation Deficit Across Multi-Model Dependencies
In multi-stage urban computing, literature frequently asserts that cross-modal feature stacking improves downstream accuracy without conducting controlled ablation studies. There is a lack of rigorous, empirical evidence isolating the marginal predictive gain ($\Delta \text{MAE}$, $\Delta R^2$) contributed by forward-looking urban growth probabilities when predicting micro-level property valuations and future-scenario routing costs.

---

## 3. Research Aim

The principal aim of this research is to design, formulate, and experimentally benchmark **GeoVerse**—a unified multi-modal spatio-temporal framework that integrates remote sensing imagery, demographic rasters, infrastructural vectors, and real estate transactions to jointly model future urban expansion, calibrate forward-looking property price surfaces, and simulate future-aware transportation accessibility scenarios across the Pune Metropolitan Region.

---

## 4. Specific Research Objectives

To achieve this aim, four measurable research objectives are defined:

* **Objective 1 (Multi-Modal Spatial-Temporal Harmonization):** Formulate a reproducible data-engineering pipeline to reproject, harmonize, and tokenize heterogeneous geospatial data (Sentinel-2 multi-spectral rasters, WorldPop population densities, OpenStreetMap highway networks, and geo-referenced property transactions) into a unified coordinate reference system ($\text{EPSG:32643}$ / UTM Zone 43N) across discrete spatial grid units ($g_i \in \mathcal{G}$) over multi-year observation horizons.
* **Objective 2 (Spatio-Temporal Urban Growth Prediction - Model 1):** Develop a spatio-temporal deep learning formulation that extracts localized spatial features and temporal transition dependencies from multi-year observation windows to generate spatially indexed, calibrated urban growth probability maps ($\tilde{U}_{i, t+k} \in [0, 1]$).
* **Objective 3 (Growth-Conditioned Property Valuation - Model 2):** Formulate a machine learning valuation model that ingests historical structural/locational property attributes augmented with forward-looking urban growth probability signals ($\tilde{U}_{i, t+k}$), and conduct a controlled ablation study to quantify the marginal error reduction ($\Delta \text{MAE}$, $\Delta \text{RMSE}$, $\Delta R^2$, $\Delta \text{MAPE}$) attributable to Model 1 growth integration.
* **Objective 4 (Future-Aware Accessibility and Scenario Routing - Model 3):** Formulate a graph-based routing algorithm over a directed road graph $G=(V, E)$ wherein edge impedance costs dynamically incorporate projected urban growth friction ($\psi(\tilde{U})$), establishing an empirical framework to compare current-state accessibility against future-scenario transit corridors.

---

## 5. Methodological Response and Evidence Alignment Matrix

The following matrix establishes strict alignment from Research Objectives to Proposed Methods, Experimental Evidence, and Evaluation Criteria, strictly following the Guidance Document standards:

| Objective | Methodological Response | Mathematical Formulation | Evaluation Metric / Evidence Expected | Target Baseline / Benchmark Comparison |
| :--- | :--- | :--- | :--- | :--- |
| **Objective 1:** Multi-Modal Harmonization | Geospatial reprojection to UTM 43N, regular tessellation (500m grid), cloud masking, z-score normalization, spatial join | Spatio-temporal tensor construction: $\mathcal{X} \in \mathbb{R}^{N \times T \times d}$ | Geometric alignment fidelity, null value distribution, spatial completeness across $1,500\text{ km}^2$ | Raw unaligned multi-resolution rasters & vector datasets |
| **Objective 2:** Urban Growth Prediction | Spatial-temporal encoder combining convolutional spatial feature extraction with temporal sequence modeling; BCE loss with class-imbalance weighting | $\tilde{U}_{i, t+k} = \sigma(f_\theta(X_{i, t-h:t}))$; $\mathcal{L}_{UG} = -\frac{1}{N}\sum [w y_i \log \tilde{U}_i + (1-y_i)\log(1-\tilde{U}_i)]$ | Precision, Recall, F1-Score, ROC-AUC, IoU | Logistic Regression, Random Forest, XGBoost, ConvLSTM, STGCN, ST-Transformer |
| **Objective 3:** Property Valuation Integration | Regression engine (Gradient Boosted Trees / Neural Regressor) evaluated with and without Model 1 growth features | $\hat{P}_{i, t+k} = g_\phi(X_{i, t}^{prop} \parallel \tilde{U}_{i, t+k})$; $\mathcal{L}_{PV} = \frac{1}{N}\sum (P_i - \hat{P}_i)^2$ | MAE (₹/sq.ft.), RMSE (₹/sq.ft.), $R^2$, MAPE (%) | Linear Regression, RF, XGBoost, LightGBM, Ablation: GeoVerse w/o growth vs. with growth |
| **Objective 4:** Future-Aware Routing | A* heuristic search over road graph $G=(V, E)$ with dynamic growth friction penalty on traversal cost | $c(e_{ij}) = \alpha \frac{D_{ij}}{D_{max}} + \beta \frac{T_{ij}}{T_{max}} + \gamma R_{ij} + \delta \psi(\tilde{U}_{ij})$ | Traversal Distance (km), Estimated Travel Time (min), Algorithmic Runtime (ms) | Standard Dijkstra, Static A*, Traffic-only shortest path |

---

## 6. Scientific Integrity & Boundary Conditions

To maintain absolute academic integrity:
1. **Model Decoupling:** GeoVerse is strictly formulated as a modular pipeline with explicit data exchanges, rather than an unverified end-to-end differentiable neural architecture.
2. **Empirical Status:** The manuscript transparently distinguishes between implemented architectural design, benchmark evaluation protocols, and future telemetry integrations (e.g., live floating-car GPS feeds).
3. **Units and Metrics:** All valuation metrics are explicitly bounded in Indian Rupees per square foot (₹/sq.ft.), distances in kilometers (km), travel times in minutes (min), and compute latencies in milliseconds (ms).

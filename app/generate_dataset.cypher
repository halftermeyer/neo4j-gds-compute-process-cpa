// ── Clean slate ───────────────────────────────────────────────────
MATCH (n) DETACH DELETE n;

// ── Large realistic DAG: 60 tasks, ~80 edges ─────────────────────
// Represents a batch risk computation pipeline with 4 phases:
//   Phase 1: Data extraction (sources)
//   Phase 2: Transformation & validation
//   Phase 3: Model computation (heavy diamonds)
//   Phase 4: Aggregation & reporting (convergence)

CREATE
  // ── Phase 1: Data Extraction (8 source tasks) ──────────────────
  (ext1:Task:Done  {uid: 1,  name: "Extract_MarketData",    duration: 3.0}),
  (ext2:Task:Done  {uid: 2,  name: "Extract_TradePositions", duration: 5.0}),
  (ext3:Task:Done  {uid: 3,  name: "Extract_Counterparties", duration: 2.0}),
  (ext4:Task:Done  {uid: 4,  name: "Extract_RiskFactors",   duration: 4.0}),
  (ext5:Task:Done  {uid: 5,  name: "Extract_HistoricalPnL",  duration: 6.0}),
  (ext6:Task:Done  {uid: 6,  name: "Extract_Collateral",     duration: 2.5}),
  (ext7:Task:Done  {uid: 7,  name: "Extract_Limits",         duration: 1.5}),
  (ext8:Task:Done  {uid: 8,  name: "Extract_Regulatory",     duration: 3.5}),

  // ── Phase 2: Transformation & Validation (16 tasks) ────────────
  (tf1:Task:Done   {uid: 10, name: "Clean_MarketData",      duration: 2.0}),
  (tf2:Task:Done   {uid: 11, name: "Clean_Positions",       duration: 3.0}),
  (tf3:Task:Done   {uid: 12, name: "Clean_Counterparties",  duration: 1.5}),
  (tf4:Task:Done   {uid: 13, name: "Clean_RiskFactors",     duration: 2.5}),
  (tf5:Task        {uid: 14, name: "Clean_HistoricalPnL",   duration: 4.0}),
  (tf6:Task:Done   {uid: 15, name: "Clean_Collateral",      duration: 1.0}),

  (val1:Task:Done  {uid: 16, name: "Validate_MarketData",   duration: 1.5}),
  (val2:Task:Done  {uid: 17, name: "Validate_Positions",    duration: 2.0}),
  (val3:Task       {uid: 18, name: "Validate_Counterparties", duration: 1.0}),
  (val4:Task       {uid: 19, name: "Validate_RiskFactors",  duration: 1.5}),
  (val5:Task       {uid: 20, name: "Validate_PnL",          duration: 2.0}),
  (val6:Task:Done  {uid: 21, name: "Validate_Collateral",   duration: 0.5}),

  (enr1:Task:Done  {uid: 22, name: "Enrich_MarketData",     duration: 3.0}),
  (enr2:Task:Done  {uid: 23, name: "Enrich_Positions",      duration: 2.5}),
  (enr3:Task       {uid: 24, name: "Enrich_Counterparties", duration: 2.0}),
  (enr4:Task       {uid: 25, name: "Enrich_RiskFactors",    duration: 3.0}),

  // ── Phase 3: Model Computation (20 tasks — heavy diamonds) ─────
  (mc1:Task:Done   {uid: 30, name: "VaR_Parametric",        duration: 8.0}),
  (mc2:Task        {uid: 31, name: "VaR_Historical",        duration: 12.0}),
  (mc3:Task        {uid: 32, name: "VaR_MonteCarlo",        duration: 15.0}),
  (mc4:Task        {uid: 33, name: "CVA_Calc",              duration: 10.0}),
  (mc5:Task        {uid: 34, name: "DVA_Calc",              duration: 9.0}),
  (mc6:Task        {uid: 35, name: "FVA_Calc",              duration: 8.0}),
  (mc7:Task        {uid: 36, name: "PFE_Simulation",        duration: 14.0}),
  (mc8:Task        {uid: 37, name: "Stress_Historical",     duration: 7.0}),
  (mc9:Task        {uid: 38, name: "Stress_Hypothetical",   duration: 6.0}),
  (mc10:Task       {uid: 39, name: "Stress_Reverse",        duration: 11.0}),

  (mc11:Task       {uid: 40, name: "Greeks_Delta",          duration: 5.0}),
  (mc12:Task       {uid: 41, name: "Greeks_Gamma",          duration: 6.0}),
  (mc13:Task       {uid: 42, name: "Greeks_Vega",           duration: 5.5}),
  (mc14:Task       {uid: 43, name: "Greeks_Theta",          duration: 4.0}),

  (mc15:Task       {uid: 44, name: "Margin_Initial",        duration: 7.0}),
  (mc16:Task       {uid: 45, name: "Margin_Variation",      duration: 5.0}),

  (mc17:Task       {uid: 46, name: "LiquidityRisk_Calc",    duration: 9.0}),
  (mc18:Task       {uid: 47, name: "ConcentrationRisk",     duration: 6.0}),
  (mc19:Task       {uid: 48, name: "CorrelationRisk",       duration: 8.0}),
  (mc20:Task       {uid: 49, name: "WrongWayRisk",          duration: 7.0}),

  // ── Phase 4: Aggregation & Reporting (16 tasks) ────────────────
  (agg1:Task       {uid: 50, name: "Agg_VaR",              duration: 3.0}),
  (agg2:Task       {uid: 51, name: "Agg_XVA",              duration: 4.0}),
  (agg3:Task       {uid: 52, name: "Agg_Stress",           duration: 3.5}),
  (agg4:Task       {uid: 53, name: "Agg_Greeks",           duration: 2.0}),
  (agg5:Task       {uid: 54, name: "Agg_Margin",           duration: 2.5}),
  (agg6:Task       {uid: 55, name: "Agg_Liquidity",        duration: 2.0}),

  (rpt1:Task       {uid: 60, name: "Report_RegulatoryVaR", duration: 4.0}),
  (rpt2:Task       {uid: 61, name: "Report_InternalRisk",  duration: 3.0}),
  (rpt3:Task       {uid: 62, name: "Report_XVA",           duration: 3.5}),
  (rpt4:Task       {uid: 63, name: "Report_StressTest",    duration: 4.0}),
  (rpt5:Task       {uid: 64, name: "Report_Margin",        duration: 2.5}),
  (rpt6:Task       {uid: 65, name: "Report_Liquidity",     duration: 2.0}),

  (final1:Task     {uid: 70, name: "RiskDashboard_Update",  duration: 5.0}),
  (final2:Task     {uid: 71, name: "RegulatorySubmission",  duration: 6.0}),
  (final3:Task     {uid: 72, name: "AlertGeneration",       duration: 2.0}),
  (final4:Task     {uid: 73, name: "EOD_Signoff",           duration: 1.0}),

  // ── Phase 1 → Phase 2 edges ────────────────────────────────────
  (ext1)-[:PRECEDES]->(tf1),
  (ext2)-[:PRECEDES]->(tf2),
  (ext3)-[:PRECEDES]->(tf3),
  (ext4)-[:PRECEDES]->(tf4),
  (ext5)-[:PRECEDES]->(tf5),
  (ext6)-[:PRECEDES]->(tf6),

  (tf1)-[:PRECEDES]->(val1),
  (tf2)-[:PRECEDES]->(val2),
  (tf3)-[:PRECEDES]->(val3),
  (tf4)-[:PRECEDES]->(val4),
  (tf5)-[:PRECEDES]->(val5),
  (tf6)-[:PRECEDES]->(val6),

  (val1)-[:PRECEDES]->(enr1),
  (val2)-[:PRECEDES]->(enr2),
  (val3)-[:PRECEDES]->(enr3),
  (val4)-[:PRECEDES]->(enr4),

  // ── Phase 2 → Phase 3 edges (diamonds) ─────────────────────────
  // VaR models need market data + positions + risk factors
  (enr1)-[:PRECEDES]->(mc1),
  (enr2)-[:PRECEDES]->(mc1),
  (enr1)-[:PRECEDES]->(mc2),
  (enr2)-[:PRECEDES]->(mc2),
  (val5)-[:PRECEDES]->(mc2),   // historical VaR needs PnL history
  (enr1)-[:PRECEDES]->(mc3),
  (enr2)-[:PRECEDES]->(mc3),
  (enr4)-[:PRECEDES]->(mc3),   // MC needs risk factors

  // XVA models need positions + counterparties
  (enr2)-[:PRECEDES]->(mc4),
  (enr3)-[:PRECEDES]->(mc4),
  (enr2)-[:PRECEDES]->(mc5),
  (enr3)-[:PRECEDES]->(mc5),
  (enr2)-[:PRECEDES]->(mc6),
  (enr3)-[:PRECEDES]->(mc6),

  // PFE needs positions + counterparties + risk factors
  (enr2)-[:PRECEDES]->(mc7),
  (enr3)-[:PRECEDES]->(mc7),
  (enr4)-[:PRECEDES]->(mc7),

  // Stress tests need market data + positions + risk factors
  (enr1)-[:PRECEDES]->(mc8),
  (enr2)-[:PRECEDES]->(mc8),
  (val5)-[:PRECEDES]->(mc8),
  (enr1)-[:PRECEDES]->(mc9),
  (enr2)-[:PRECEDES]->(mc9),
  (enr4)-[:PRECEDES]->(mc9),
  (enr1)-[:PRECEDES]->(mc10),
  (enr2)-[:PRECEDES]->(mc10),
  (enr4)-[:PRECEDES]->(mc10),

  // Greeks need market data + positions
  (enr1)-[:PRECEDES]->(mc11),
  (enr2)-[:PRECEDES]->(mc11),
  (enr1)-[:PRECEDES]->(mc12),
  (enr2)-[:PRECEDES]->(mc12),
  (enr1)-[:PRECEDES]->(mc13),
  (enr2)-[:PRECEDES]->(mc13),
  (enr1)-[:PRECEDES]->(mc14),
  (enr2)-[:PRECEDES]->(mc14),

  // Margin needs positions + collateral
  (enr2)-[:PRECEDES]->(mc15),
  (val6)-[:PRECEDES]->(mc15),
  (enr2)-[:PRECEDES]->(mc16),
  (val6)-[:PRECEDES]->(mc16),

  // Liquidity & concentration need positions + limits
  (enr2)-[:PRECEDES]->(mc17),
  (ext7)-[:PRECEDES]->(mc17),
  (enr2)-[:PRECEDES]->(mc18),
  (ext7)-[:PRECEDES]->(mc18),

  // Correlation & wrong-way risk need counterparties + risk factors
  (enr3)-[:PRECEDES]->(mc19),
  (enr4)-[:PRECEDES]->(mc19),
  (enr3)-[:PRECEDES]->(mc20),
  (mc4)-[:PRECEDES]->(mc20),   // wrong-way risk depends on CVA

  // ── Phase 3 → Phase 4 edges (aggregation) ──────────────────────
  (mc1)-[:PRECEDES]->(agg1),
  (mc2)-[:PRECEDES]->(agg1),
  (mc3)-[:PRECEDES]->(agg1),

  (mc4)-[:PRECEDES]->(agg2),
  (mc5)-[:PRECEDES]->(agg2),
  (mc6)-[:PRECEDES]->(agg2),

  (mc8)-[:PRECEDES]->(agg3),
  (mc9)-[:PRECEDES]->(agg3),
  (mc10)-[:PRECEDES]->(agg3),

  (mc11)-[:PRECEDES]->(agg4),
  (mc12)-[:PRECEDES]->(agg4),
  (mc13)-[:PRECEDES]->(agg4),
  (mc14)-[:PRECEDES]->(agg4),

  (mc15)-[:PRECEDES]->(agg5),
  (mc16)-[:PRECEDES]->(agg5),

  (mc17)-[:PRECEDES]->(agg6),
  (mc18)-[:PRECEDES]->(agg6),

  // ── Aggregation → Reports ──────────────────────────────────────
  (agg1)-[:PRECEDES]->(rpt1),
  (ext8)-[:PRECEDES]->(rpt1),  // regulatory report needs regulatory data

  (agg1)-[:PRECEDES]->(rpt2),
  (agg4)-[:PRECEDES]->(rpt2),

  (agg2)-[:PRECEDES]->(rpt3),
  (mc20)-[:PRECEDES]->(rpt3),  // XVA report includes wrong-way risk

  (agg3)-[:PRECEDES]->(rpt4),

  (agg5)-[:PRECEDES]->(rpt5),

  (agg6)-[:PRECEDES]->(rpt6),
  (mc19)-[:PRECEDES]->(rpt6),  // liquidity report includes correlation

  // ── Reports → Final outputs ────────────────────────────────────
  (rpt1)-[:PRECEDES]->(final1),
  (rpt2)-[:PRECEDES]->(final1),
  (rpt3)-[:PRECEDES]->(final1),
  (rpt4)-[:PRECEDES]->(final1),
  (rpt5)-[:PRECEDES]->(final1),
  (rpt6)-[:PRECEDES]->(final1),

  (rpt1)-[:PRECEDES]->(final2),
  (rpt4)-[:PRECEDES]->(final2),
  (mc7)-[:PRECEDES]->(final2),   // PFE goes directly to regulatory

  (rpt1)-[:PRECEDES]->(final3),
  (rpt2)-[:PRECEDES]->(final3),

  (final1)-[:PRECEDES]->(final4),
  (final2)-[:PRECEDES]->(final4),
  (final3)-[:PRECEDES]->(final4)

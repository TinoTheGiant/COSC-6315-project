// Midterm deck for COSC 6315.
//
// Built as a structured deck: one theme, named layouts, placeholders, sections.
// Every number on a slide comes from results/recorded/*.csv in the project
// repository, and every slide carries one plain sentence saying what the
// number means.

const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/root/.claude/skills/synced/7fdc08fc-504c-450a-abcb-7609c84bf1f4_7c51a4df-7473-4ac7-b49f-50ff0547230b/pptx/scripts/apply_theme.js");

const THEME = {
  name: "Fragalloc Midterm",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "15181C",      // body text on light
    lt1: "FFFFFF",      // light background
    dk2: "0E2A4E",      // deep navy, dark slides
    lt2: "F3F1EC",      // warm off-white, cards
    accent1: "184F95",  // the blue used for the learned policy in the paper
    accent2: "2B7A78",  // teal
    accent3: "8A8782",  // warm grey, baselines
    accent4: "B8A24A",  // muted gold, one highlight only
    accent5: "4A6B8A",
    accent6: "C2BDB4",
    hlink: "184F95",
    folHlink: "2B7A78",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";          // 13.3 x 7.5 inches
pres.author = "Tino Kaseke";
pres.company = "University of Texas Permian Basin";
pres.subject = "Reinforcement Learning for Dynamic Data Fragmentation and Allocation";
pres.title = "RL for Dynamic Data Fragmentation and Allocation";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const C = pres.SchemeColor;
const M = 0.75;                        // page margin
const W = 13.33;

// ---------------------------------------------------------------- layouts

pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: M, y: 1.92, w: 10, h: 0.35,
        fontSize: 13, color: C.accent6, charSpacing: 2, bold: true, align: "left" }, text: " " } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.45, w: 11.3, h: 2.0,
        fontSize: 40, color: C.background1, lineSpacing: 46, align: "left" }, text: " " } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.75, w: 10, h: 1.4,
        fontSize: 16, color: C.accent6, lineSpacing: 24, align: "left" }, text: " " } },
    { rect: { x: M, y: 1.78, w: 1.5, h: 0.035, fill: { color: THEME.colors.accent4 } } },
  ],
});

pres.defineSlideMaster({
  title: "DIVIDER",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: M, y: 2.49, w: 10, h: 0.35,
        fontSize: 13, color: C.accent6, charSpacing: 2, bold: true, align: "left" }, text: " " } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 3.0, w: 11.3, h: 1.6,
        fontSize: 34, color: C.background1, lineSpacing: 42, align: "left" }, text: " " } },
    { rect: { x: M, y: 2.35, w: 1.5, h: 0.035, fill: { color: THEME.colors.accent4 } } },
  ],
});

// The workhorse. Everything else is composed on top of it slide by slide.
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.45, w: 11.8, h: 0.85,
        fontSize: 25, color: C.text2, lineSpacing: 30, align: "left" }, text: " " } },
    { rect: { x: M, y: 1.33, w: 1.1, h: 0.035, fill: { color: THEME.colors.accent4 } } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 1.55, w: 11.8, h: 0.6,
        fontSize: 15, color: C.text1, lineSpacing: 21, align: "left" }, text: " " } },
    { text: { text: "Tino Kaseke  |  COSC 6315 midterm  |  26 October 2026",
        options: { x: M, y: 6.95, w: 8, h: 0.3, fontSize: 9.5, color: THEME.colors.accent3 } } },
    { placeholder: { options: { name: "source", type: "body", x: 8.0, y: 6.95, w: 4.58, h: 0.3,
        fontSize: 9.5, color: THEME.colors.accent3, align: "right" }, text: " " } },
    { slideNumber: { x: 12.9, y: 0.35, w: 0.3, h: 0.3, fontSize: 10, color: THEME.colors.accent3 } },
  ],
});

// ---------------------------------------------------------------- helpers

/** A tinted card. The deck's one repeated shape. */
function card(slide, { x, y, w, h, name, fill }) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.06,
    fill: { color: fill || THEME.colors.lt2 },
    line: { color: THEME.colors.accent6, width: 0.5 },
    objectName: name,
  });
}

/** Big number with a small label under it, inside a card. */
function stat(slide, { x, y, w, value, label, color, h }) {
  const height = h || 1.5;
  card(slide, { x, y, w, h: height, name: `stat-${label.slice(0, 18)}` });
  slide.addText(value, {
    x: x + 0.15, y: y + 0.14, w: w - 0.3, h: 0.72, isTextBox: true, margin: 0,
    fontSize: 34, bold: true, color: color || THEME.colors.accent1,
    fontFace: THEME.headFontFace, align: "center", valign: "middle",
  });
  slide.addText(label, {
    x: x + 0.15, y: y + 0.84, w: w - 0.3, h: height - 0.95, isTextBox: true, margin: 0,
    fontSize: 11.5, color: THEME.colors.dk1, align: "center", valign: "top", lineSpacing: 15,
  });
}

/** The explaining line every slide carries, set apart from the body text. */
function plain(slide, text, y) {
  slide.addText([{ text: "In plain terms:  ", options: { bold: true, color: THEME.colors.accent2 } },
                 { text }], {
    x: M, y: y, w: 11.8, h: 0.6, isTextBox: true, margin: 0,
    fontSize: 13.5, color: THEME.colors.dk1, lineSpacing: 19, objectName: "plain-english",
  });
}

const CHART_BASE = {
  showLegend: false,
  catAxisLabelColor: THEME.colors.accent3,
  valAxisLabelColor: THEME.colors.accent3,
  catAxisLabelFontFace: "+mn-lt",
  valAxisLabelFontFace: "+mn-lt",
  catAxisLabelFontSize: 11,
  valAxisLabelFontSize: 11,
  dataLabelFontFace: "+mn-lt",
  dataLabelFontSize: 11,
  dataLabelColor: THEME.colors.dk1,
  valGridLine: { color: "E3E0DA", size: 0.75 },
  catGridLine: { style: "none" },
  chartColors: [THEME.colors.accent1, THEME.colors.accent3, THEME.colors.accent2],
};

// ============================================================ 1. title

pres.addSection({ title: "Opening" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Opening" });
s.addText("COSC 6315  ·  MIDTERM PROGRESS", { placeholder: "eyebrow" });
s.addText("Reinforcement Learning for Dynamic\nData Fragmentation and Allocation",
  { placeholder: "title" });
s.addText("Tino Kaseke  ·  Department of Computer Science\nUniversity of Texas Permian Basin  ·  26 October 2026",
  { placeholder: "body" });
s.addNotes(
  "Midterm progress for COSC 6315. The project asks whether a reinforcement learning agent " +
  "can move database shards around a multi-region cluster in real time, better than a simple " +
  "rule that reacts to recent traffic. Everything on these slides is measured and comes from " +
  "recorded run directories in the project repository.");

// ============================================================ 2. problem

pres.addSection({ title: "The problem" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The problem" });
s.addText("A database decides where to put its data once, and the traffic does not stay put",
  { placeholder: "title" });
s.addText("A shard is a group of database records. Which machine holds each shard is normally decided by a function of the key, such as a hash. A hash does not know where the requests are coming from.",
  { placeholder: "body" });

card(s, { x: M, y: 2.45, w: 5.7, h: 3.1, name: "card-today" });
s.addText("How it works today", { x: M + 0.3, y: 2.65, w: 5.1, h: 0.4, isTextBox: true, margin: 0,
  fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "Shard boundaries are fixed by the schema at design time", options: { bullet: true, breakLine: true } },
  { text: "Placement is a hash of the key, blind to geography", options: { bullet: true, breakLine: true } },
  { text: "Neither decision is ever revisited", options: { bullet: true } },
], { x: M + 0.3, y: 3.1, w: 5.1, h: 1.6, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 8, lineSpacing: 18 });

card(s, { x: 6.9, y: 2.45, w: 5.68, h: 3.1, name: "card-cost" });
s.addText("What it costs", { x: 7.2, y: 2.65, w: 5.1, h: 0.4, isTextBox: true, margin: 0,
  fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "The busiest region moves across the day as one wakes and another sleeps", options: { bullet: true, breakLine: true } },
  { text: "Every request that crosses an ocean pays that ocean's round trip", options: { bullet: true, breakLine: true } },
  { text: "A transaction touching shards in several regions pays it more than once", options: { bullet: true } },
], { x: 7.2, y: 3.1, w: 5.1, h: 1.6, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 8, lineSpacing: 18 });

plain(s, "A placement chosen for the morning is wrong by the evening, and the database has no way to notice.", 5.9);
s.addText("", { placeholder: "source" });
s.addNotes(
  "Set up the problem for an audience that has not worked on distributed databases. " +
  "A shard is just a group of records. The two design-time decisions are where shard " +
  "boundaries fall and which machine holds each shard. A hash spreads keys evenly, which " +
  "is good for load, but it never looks at where requests originate, which is bad for latency " +
  "once users are spread across continents.");

// ============================================================ 3. question

s = pres.addSlide({ masterName: "DIVIDER", sectionTitle: "The problem" });
s.addText("THE QUESTION", { placeholder: "eyebrow" });
s.addText("Can a policy learned from experience place data better\nthan a simple rule that follows the traffic?",
  { placeholder: "title" });
s.addText("The simple rule is the opponent. Every decision window, find the shard whose placement is costing the most and move it towards the region reading it. I call it follow traffic.",
  { x: M, y: 4.75, w: 10.6, h: 1.1, isTextBox: true, margin: 0, fontSize: 15,
    color: "C2BDB4", lineSpacing: 22, objectName: "divider-note" });
s.addNotes(
  "This is the question the whole project turns on. The honest answer, measured rather than " +
  "assumed, is that it depends on how fast the traffic moves. That finding is slides 10 and 11.");

// ============================================================ 4. built

pres.addSection({ title: "What I built" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "What I built" });
s.addText("What is built: a simulator, four baselines, an agent, and a real cluster",
  { placeholder: "title" });
s.addText("The agent is trained against the simulator, which is fast and cheap, and is meant to be fine-tuned against the real cluster, which is slow and real.",
  { placeholder: "body" });
s.addImage({ path: "arch.png", x: 1.35, y: 2.35, w: 7.4, h: 3.12, objectName: "architecture" });

card(s, { x: 9.0, y: 2.35, w: 3.58, h: 3.12, name: "card-parity" });
s.addText("Three things must match", { x: 9.25, y: 2.5, w: 3.1, h: 0.4, isTextBox: true, margin: 0,
  fontSize: 14, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "What the agent sees", options: { bullet: true, breakLine: true } },
  { text: "What the agent can do", options: { bullet: true, breakLine: true } },
  { text: "How cost is charged", options: { bullet: true, breakLine: true } },
  { text: "If any of the three differs between the two sides, a policy trained in one means nothing in the other.", options: {} },
], { x: 9.25, y: 2.9, w: 3.1, h: 2.2, isTextBox: true, margin: 0, fontSize: 12.5,
     color: THEME.colors.dk1, paraSpaceAfter: 7, lineSpacing: 17 });

plain(s, "Train in the cheap copy, run on the real thing. That only works if the cheap copy charges for a move exactly the way the real one does.", 5.9);
s.addText("Rubric: implementation and architecture", { placeholder: "source" });
s.addNotes(
  "Rubric item 1, implementation. The simulator holds the shard catalogue, the workload " +
  "generator, the action handler and the cost model. A Gymnasium wrapper turns each decision " +
  "window into an observation and a reward, and Stable-Baselines3 trains the Deep Q-Network " +
  "against it. The learned policy satisfies the same interface as the baselines and runs " +
  "through the same episode loop, so a difference between two numbers in this deck cannot be " +
  "a difference between two pieces of harness code. The cluster harness that would let the " +
  "trained agent act on real hardware is not built yet.");

// ============================================================ 5. actions

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "What I built" });
s.addText("What the agent can do, and what it is scored on", { placeholder: "title" });
s.addText("At each decision window the agent sees the read and write counts per region, where every shard sits, how big it is, and the round-trip times between regions. It then picks one action out of 261.",
  { placeholder: "body" });

const ACTIONS = [
  ["Move the primary", "Make a region the main copy for a shard. Moves no data."],
  ["Move a replica", "Put a copy in a region, dropping the furthest one. Moves data."],
  ["Split a shard", "Divide one shard into two at its midpoint."],
  ["Do nothing", "Leave the placement alone this window."],
];
ACTIONS.forEach(([name, desc], i) => {
  const x = M + i * 3.03;
  card(s, { x, y: 2.5, w: 2.83, h: 1.5, name: `action-${i}` });
  s.addText(name, { x: x + 0.18, y: 2.65, w: 2.47, h: 0.35, isTextBox: true, margin: 0,
    fontSize: 14, bold: true, color: THEME.colors.accent1, fontFace: THEME.headFontFace });
  s.addText(desc, { x: x + 0.18, y: 3.02, w: 2.47, h: 0.9, isTextBox: true, margin: 0,
    fontSize: 11.5, color: THEME.colors.dk1, lineSpacing: 15 });
});

card(s, { x: M, y: 4.2, w: 11.83, h: 1.35, name: "card-score", fill: "0E2A4E" });
s.addText("The score it minimises", { x: M + 0.3, y: 4.35, w: 3.4, h: 0.35, isTextBox: true,
  margin: 0, fontSize: 14, bold: true, color: "FFFFFF", fontFace: THEME.headFontFace });
s.addText([
  { text: "latency ", options: { color: "9FC2EA", bold: true } },
  { text: "+  how much data it moved  +  how unevenly it loaded the nodes", options: { color: "FFFFFF" } },
], { x: M + 0.3, y: 4.72, w: 7.2, h: 0.4, isTextBox: true, margin: 0, fontSize: 16,
     fontFace: THEME.headFontFace });
s.addText("Movement is charged as a fraction of the dataset, not in bytes, so a 60 GB simulator and a 1 GB cluster score the same physical move identically.",
  { x: 8.1, y: 4.38, w: 4.2, h: 1.0, isTextBox: true, margin: 0, fontSize: 11.5,
    color: "C2BDB4", lineSpacing: 15 });

plain(s, "Imbalance is charged separately so the agent cannot win on speed by piling the whole workload onto one node.", 5.75);
s.addText("Rubric: implementation and architecture", { placeholder: "source" });
s.addNotes(
  "Every action names a desired end state rather than an operation, so every action is defined " +
  "in every state and one that cannot be applied resolves to a small penalty instead of an " +
  "error. That matters because a Deep Q-Network cannot be told which actions are illegal. " +
  "The exact cost is latency over 100, plus the movement weight times gigabytes over 2000, " +
  "plus 0.10 times imbalance. Lower is better.");

// ============================================================ 6. setup

pres.addSection({ title: "How it is measured" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "How it is measured" });
s.addText("How the experiments are run", { placeholder: "title" });
s.addText("One script writes one self-contained directory per run, holding the settings, the seeds, the commit, the machine and the command that reproduces it. Runs execute on hosted continuous integration, not on my laptop.",
  { placeholder: "body" });

s.addTable([
  [{ text: "Setting", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" } } },
   { text: "Value", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" } } }],
  ["Regions", "6, one node each, 3 copies per shard"],
  ["Keyspace", "256 cells, 6 starting shards, 20 shard cap, 60 GB"],
  ["Episode", "200 decision windows; a simulated day is 96"],
  ["Per window", "8,000 single-key requests, 2,000 three-key transactions, 80% reads"],
  ["Agent", "Deep Q-Network, two 256-unit layers, 261 actions"],
  ["Training", "300,000 to 1,000,000 steps, rotating through 64 seeds"],
  ["Cluster", "6 CockroachDB nodes, wide-area delays injected with netem"],
], {
  x: M, y: 2.45, w: 7.4, colW: [1.8, 5.6], fontSize: 11.5, color: THEME.colors.dk1,
  border: { type: "solid", color: "E3E0DA", pt: 0.5 }, rowH: 0.33, valign: "middle",
  objectName: "config-table",
});

card(s, { x: 8.45, y: 2.45, w: 4.13, h: 1.5, name: "card-baselines" });
s.addText("Four things to beat", { x: 8.7, y: 2.6, w: 3.6, h: 0.3, isTextBox: true, margin: 0,
  fontSize: 13.5, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText("Fixed placement, random movement, the follow traffic rule, and a cost-free reference that shows what good placement is worth when movement is free.",
  { x: 8.7, y: 2.94, w: 3.6, h: 0.9, isTextBox: true, margin: 0, fontSize: 11.5,
    color: THEME.colors.dk1, lineSpacing: 15 });

card(s, { x: 8.45, y: 4.1, w: 4.13, h: 1.4, name: "card-seeds" });
s.addText("Seeds kept apart", { x: 8.7, y: 4.25, w: 3.6, h: 0.3, isTextBox: true, margin: 0,
  fontSize: 13.5, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText("The sweep uses seeds 0 to 7. The agent is evaluated on seeds 2000 to 2007, which training refuses to touch. The two blocks never share a table.",
  { x: 8.7, y: 4.59, w: 3.6, h: 0.85, isTextBox: true, margin: 0, fontSize: 11.5,
    color: THEME.colors.dk1, lineSpacing: 15 });

plain(s, "The agent is tested on workloads it has never trained on, so a good score cannot be memorisation.", 5.7);
s.addText("Rubric: experimental setup and baselines", { placeholder: "source" });
s.addNotes(
  "Rubric item 2, experimental setup. The point of the random baseline is to separate two " +
  "explanations: does the gain come from moving data, or from choosing where to move it. " +
  "The cost-free reference keeps the shard boundaries the episode started with, so it is not " +
  "a global optimum and a policy that splits a shard can legitimately score below it.");

// ============================================================ 7. divider

pres.addSection({ title: "Results" });
s = pres.addSlide({ masterName: "DIVIDER", sectionTitle: "Results" });
s.addText("PRELIMINARY RESULTS", { placeholder: "eyebrow" });
s.addText("Four measurements, in the order they were needed",
  { placeholder: "title" });
s.addText("Does placement matter on real hardware?  ·  Does moving data help by itself?  ·  How much room is there for a better policy?  ·  Does the agent use it?",
  { x: M, y: 4.6, w: 11.3, h: 1.0, isTextBox: true, margin: 0, fontSize: 15,
    color: "C2BDB4", lineSpacing: 22, objectName: "divider-note" });
s.addNotes("Each of the next four slides answers one of these, in order.");

// ============================================================ 8. cluster

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Placement changes latency on real hardware, by a lot", { placeholder: "title" });
s.addText("Six CockroachDB nodes on one host with wide-area delays injected between them. The same transactions ran twice: once with the main copies gathered in the region issuing them, once with them spread out.",
  { placeholder: "body" });

s.addChart(pres.charts.BAR, [
  { name: "Main copies gathered", labels: ["Median", "95th percentile"], values: [272.7, 275.5] },
  { name: "Main copies spread", labels: ["Median", "95th percentile"], values: [1013.4, 1648.0] },
], Object.assign({}, CHART_BASE, {
  x: M, y: 2.35, w: 7.6, h: 3.1, barDir: "col", barGapWidthPct: 60,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0",
  showLegend: true, legendPos: "b", legendFontFace: "+mn-lt", legendFontSize: 11,
  legendColor: THEME.colors.dk1,
  chartColors: [THEME.colors.accent1, THEME.colors.accent3],
  valAxisTitle: "transaction latency (ms)", showValAxisTitle: true,
  valAxisTitleFontFace: "+mn-lt", valAxisTitleFontSize: 11,
  valAxisTitleColor: THEME.colors.accent3, valAxisMinVal: 0, valAxisMaxVal: 1900,
  objectName: "cluster-chart",
}));

stat(s, { x: 8.5, y: 2.45, w: 4.08, value: "1,373 ms",
  label: "difference at the 95th percentile between gathered and spread, first pilot" });
stat(s, { x: 8.5, y: 4.1, w: 4.08, value: "1,202 ms",
  label: "the same difference in the second pilot, with five times the transactions" });

plain(s, "Where the main copy of a shard sits is worth more than a second of delay on the slowest transactions. That is the assumption everything else rests on.", 5.75);
s.addText("Cluster pilots 2 and 3", { placeholder: "source" });
s.addNotes(
  "Rubric item 3. Gathered means the main copies, not the data. With three copies and one " +
  "node per region the copies always span three regions, so every write still pays a " +
  "cross-region agreement even in the gathered case. That is why the gathered median is " +
  "272.7 ms rather than single digits. What this isolates is the effect of where the main " +
  "copy sits, which is exactly what the move-the-primary action controls. " +
  "One caveat worth saying out loud: the gathered case became 62 percent slower when the " +
  "second pilot moved from two cores to four, which is consistent with every main copy " +
  "landing on one node and that node becoming the limit. The simulator cannot reproduce that, " +
  "and it is why imbalance is charged for separately.");

// ============================================================ 9. random

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Moving data buys nothing. Choosing where to move it buys everything",
  { placeholder: "title" });
s.addText("The random baseline moves data at the same rate as the rule, but picks destinations without looking at the traffic. It is the control that separates the two explanations.",
  { placeholder: "body" });

s.addTable([
  [{ text: "Method", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" } } },
   { text: "Mean latency (ms)", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" }, align: "right" } },
   { text: "Data moved (GB)", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" }, align: "right" } },
   { text: "What it shows", options: { bold: true, color: "FFFFFF", fill: { color: "0E2A4E" } } }],
  ["Fixed placement", { text: "156.11", options: { align: "right" } }, { text: "0.0", options: { align: "right" } }, "Doing nothing"],
  ["Random movement", { text: "158.02", options: { align: "right" } }, { text: "204.8", options: { align: "right" } }, "Moved a lot, gained nothing"],
  [{ text: "Follow traffic", options: { bold: true } },
   { text: "98.66", options: { align: "right", bold: true } },
   { text: "785.2", options: { align: "right", bold: true } },
   { text: "36.8% faster than fixed", options: { bold: true } }],
  ["Cost-free reference", { text: "93.66", options: { align: "right" } }, { text: "not charged", options: { align: "right" } }, "What good placement is worth"],
], {
  x: M, y: 2.5, w: 11.83, colW: [2.6, 2.3, 2.3, 4.63], fontSize: 13,
  color: THEME.colors.dk1, border: { type: "solid", color: "E3E0DA", pt: 0.5 },
  rowH: 0.52, valign: "middle", objectName: "baseline-table",
});

plain(s, "Random movement shifted 205 GB of data and ended up no faster than leaving everything where it was. All of the gain is in the choice of destination, which is why this is a decision problem worth learning.", 5.65);
s.addText("Volatility 1.0, eight seeds, 200 windows", { placeholder: "source" });
s.addNotes(
  "Eight seeds per row, 200 decision windows per episode, at volatility 1.0. The 36.8 percent " +
  "is (156.11 minus 98.66) over 156.11. The reference is not charged for movement at all, " +
  "which is why its movement column says not charged rather than zero.");

// ============================================================ 10. sweep

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("The faster the traffic moves, the more room there is for a better policy",
  { placeholder: "title" });
s.addText("Volatility is one number that scales how fast the busiest region rotates and how hard it spikes. Here it is swept over a factor of eight.",
  { placeholder: "body" });

s.addChart(pres.charts.LINE, [
  { name: "Fixed placement", labels: ["0.5", "1.0", "2.0", "4.0"], values: [156.27, 156.11, 155.37, 155.77] },
  { name: "Follow traffic", labels: ["0.5", "1.0", "2.0", "4.0"], values: [94.31, 98.66, 125.37, 139.58] },
  { name: "Cost-free reference", labels: ["0.5", "1.0", "2.0", "4.0"], values: [93.87, 93.66, 89.47, 82.38] },
], Object.assign({}, CHART_BASE, {
  x: M, y: 2.3, w: 7.6, h: 3.15, lineSize: 3, lineSmooth: false,
  showLegend: true, legendPos: "b", legendFontFace: "+mn-lt", legendFontSize: 11,
  legendColor: THEME.colors.dk1,
  chartColors: [THEME.colors.accent3, THEME.colors.accent1, THEME.colors.accent2],
  catAxisTitle: "how fast the traffic moves", showCatAxisTitle: true,
  catAxisTitleFontFace: "+mn-lt", catAxisTitleFontSize: 11,
  catAxisTitleColor: THEME.colors.accent3,
  valAxisTitle: "mean latency (ms)", showValAxisTitle: true,
  valAxisTitleFontFace: "+mn-lt", valAxisTitleFontSize: 11,
  valAxisTitleColor: THEME.colors.accent3,
  valAxisMinVal: 60, valAxisMaxVal: 170,
  objectName: "sweep-chart",
}));

stat(s, { x: 8.5, y: 2.4, w: 1.95, value: "0.44", color: THEME.colors.accent3,
  label: "ms between the rule and the reference, slow drift", h: 1.6 });
stat(s, { x: 10.63, y: 2.4, w: 1.95, value: "57.20", color: THEME.colors.accent1,
  label: "ms between them at the fastest setting", h: 1.6 });
card(s, { x: 8.5, y: 4.15, w: 4.08, h: 1.3, name: "card-sweep-note" });
s.addText("The rule also moves more: 405 GB per episode at the slowest setting, 1,115 GB at the fastest. It pays nearly three times as much and gets less for it.",
  { x: 8.75, y: 4.32, w: 3.6, h: 1.0, isTextBox: true, margin: 0, fontSize: 12,
    color: THEME.colors.dk1, lineSpacing: 16 });

plain(s, "Fixed placement is flat because it was never tracking anything. The reference gets better because sharper traffic is easier to serve well. The rule gets worse because it always reacts one window late.", 5.7);
s.addText("Volatility sweep, eight seeds per setting", { placeholder: "source" });
s.addNotes(
  "This is the slide the project turns on. Three things happen at once. Fixed placement is " +
  "flat, 155 to 156 ms across the whole sweep, because it was never tracking the traffic. " +
  "The cost-free reference improves, 93.87 down to 82.38, which reads backwards at first: " +
  "faster drift means the traffic is more sharply concentrated at any one moment, and sharply " +
  "concentrated traffic is easier to serve well if the data is in the right place. And the " +
  "rule gets worse, 94.31 up to 139.58, because it reacts to the window just finished whilst " +
  "the target has already moved on. The gap at the fastest setting is 41 percent of the " +
  "rule's own latency. So the case for learning is conditional on volatility, and this " +
  "measures the condition rather than assuming it.");

// ============================================================ 11. agent

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("At the hardest setting the learned agent beats both baselines",
  { placeholder: "title" });
s.addText("Scored on the full cost, not on latency alone, because latency is the only term the rule is trying to minimise. Lower is better.",
  { placeholder: "body" });

s.addChart(pres.charts.BAR, [
  { name: "Combined cost", labels: ["Fixed placement", "Follow traffic", "Learned agent"],
    values: [1.557, 1.554, 1.486] },
], Object.assign({}, CHART_BASE, {
  x: M, y: 2.35, w: 7.0, h: 3.0, barDir: "col", barGapWidthPct: 70,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000",
  chartColors: [THEME.colors.accent3, THEME.colors.accent3, THEME.colors.accent1],
  valAxisMinVal: 1.4, valAxisMaxVal: 1.62,
  valAxisTitle: "combined cost at the fastest setting", showValAxisTitle: true,
  valAxisTitleFontFace: "+mn-lt", valAxisTitleFontSize: 11,
  valAxisTitleColor: THEME.colors.accent3,
  objectName: "objective-chart",
}));

stat(s, { x: 7.95, y: 2.4, w: 2.25, value: "11 ms", color: THEME.colors.accent3,
  label: "slower than the rule on latency", h: 1.45 });
stat(s, { x: 10.33, y: 2.4, w: 2.25, value: "1/20", color: THEME.colors.accent1,
  label: "of the data the rule moves", h: 1.45 });
card(s, { x: 7.95, y: 4.0, w: 4.63, h: 1.35, name: "card-agent-note" });
s.addText("62.7 GB moved against the rule's 1,086.5 GB, on two independent training seeds. Fixed placement is beaten in every run recorded.",
  { x: 8.2, y: 4.18, w: 4.15, h: 1.0, isTextBox: true, margin: 0, fontSize: 12,
    color: THEME.colors.dk1, lineSpacing: 16 });

plain(s, "The agent is slower than the rule but far cheaper, and the rule has by this point stopped beating fixed placement at all. Everything the rule gains on speed it hands back in movement and uneven load.", 5.6);
s.addText("Held-out seeds 2000 to 2007", { placeholder: "source" });
s.addNotes(
  "Each pair is scored at the same movement weight, because scoring a learned run against a " +
  "baseline measured at a different weight compares a policy with a differently judged " +
  "opponent. That arithmetic is produced by a script in the repository rather than by hand, " +
  "after it went wrong once by hand. " +
  "The second result on this slide is the one people miss: at the fastest setting the rule " +
  "and fixed placement are 1.554 and 1.557, indistinguishable, even though the rule is 21 ms " +
  "faster. The reactive rule has stopped being worth running.");

// ============================================================ 12. caveats

pres.addSection({ title: "Honest state" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Honest state" });
s.addText("What is not true yet", { placeholder: "title" });
s.addText("The win is narrow, over an opponent that has itself stopped working. Four things qualify it, and they are substantial.",
  { placeholder: "body" });

const CAVEATS = [
  ["Nothing has converged", "Every run was still improving at its last training step. The numbers are a floor, not a ceiling."],
  ["Most actions do nothing", "Between 79.9% and 89.8% of the actions the agent picks cannot be applied in the state it picked them. Random is 80.4%."],
  ["The seeds disagree more than the settings do", "Two training seeds differ by 4.70 ms; changing the movement weight changes latency by 2.97 ms. So nothing can be claimed about that weight yet."],
  ["The reference is still far away", "The agent scores 1.486 against the reference's 0.813. The distance left is larger than the distance closed."],
];
CAVEATS.forEach(([head, body], i) => {
  const x = M + i * 3.03;
  card(s, { x, y: 2.45, w: 2.83, h: 3.1, name: `caveat-${i}` });
  s.addShape(pres.shapes.OVAL, { x: x + 0.18, y: 2.62, w: 0.34, h: 0.34,
    fill: { color: THEME.colors.accent4 }, objectName: `caveat-dot-${i}` });
  s.addText(String(i + 1), { x: x + 0.18, y: 2.62, w: 0.34, h: 0.34, isTextBox: true, margin: 0,
    fontSize: 13, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
  s.addText(head, { x: x + 0.18, y: 3.05, w: 2.47, h: 0.72, isTextBox: true, margin: 0,
    fontSize: 13.5, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace,
    lineSpacing: 17 });
  s.addText(body, { x: x + 0.18, y: 3.8, w: 2.47, h: 1.2, isTextBox: true, margin: 0,
    fontSize: 11.5, color: THEME.colors.dk1, lineSpacing: 15 });
});

plain(s, "The agent is winning on the minority of its decisions that actually land. Fixing the action space is the first job, not more training.", 5.9);
s.addText("", { placeholder: "source" });
s.addNotes(
  "Say these out loud rather than leaving them in a backup slide. The inapplicable-action rate " +
  "is the largest measured inefficiency in the project and it is a known failure mode as the " +
  "illegal share of an action list grows. Action elimination networks built on this kind of " +
  "agent address it directly, and that is the first thing on the list after the midterm.");

// ============================================================ 13. next

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Honest state" });
s.addText("The paper, and what happens next", { placeholder: "title" });
s.addText("The midterm paper is five pages in IEEE two-column format: introduction, related work, system design, experimental method, preliminary results, discussion, limitations, conclusion.",
  { placeholder: "body" });

card(s, { x: M, y: 2.45, w: 5.7, h: 3.1, name: "card-paper" });
s.addText("In the paper", { x: M + 0.3, y: 2.62, w: 5.1, h: 0.35, isTextBox: true, margin: 0,
  fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "The four measurements on the last four slides, with their qualifications", options: { bullet: true, breakLine: true } },
  { text: "Three figures and three tables, every number traced to a recorded run", options: { bullet: true, breakLine: true } },
  { text: "Fourteen references, all verified against Crossref", options: { bullet: true, breakLine: true } },
  { text: "A disclosure of AI use", options: { bullet: true } },
], { x: M + 0.3, y: 3.05, w: 5.1, h: 2.1, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 9, lineSpacing: 18 });

card(s, { x: 6.9, y: 2.45, w: 5.68, h: 3.1, name: "card-next" });
s.addText("Next, in this order", { x: 7.2, y: 2.62, w: 5.1, h: 0.35, isTextBox: true, margin: 0,
  fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "Stop the agent picking actions it cannot use", options: { bullet: true, breakLine: true } },
  { text: "More seeds per setting, which is cheap and unblocks the movement-weight question", options: { bullet: true, breakLine: true } },
  { text: "Credit a move with the latency it saves later, not charge it all at once", options: { bullet: true, breakLine: true } },
  { text: "Build the harness that lets the trained agent act on the real cluster", options: { bullet: true } },
], { x: 7.2, y: 3.05, w: 5.1, h: 2.1, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 9, lineSpacing: 18 });

plain(s, "The next experiment is not a longer training run. It is making the agent's choices count.", 5.9);
s.addText("Rubric: paper and remaining plan", { placeholder: "source" });
s.addNotes(
  "Rubric item 4, the paper. The longer versions of each section are kept in the repository " +
  "for the final paper; the midterm draft is deliberately short and written for a reader who " +
  "knows computer science but not distributed databases.");

// ============================================================ 14. disclosure

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Honest state" });
s.addText("Disclosure of AI use", { placeholder: "title" });
s.addText("Claude, by Anthropic, was used throughout this project as a coding and writing assistant.",
  { placeholder: "body" });

card(s, { x: M, y: 2.45, w: 5.7, h: 3.1, name: "card-ai-did" });
s.addText("What it did", { x: M + 0.3, y: 2.58, w: 5.1, h: 0.35, isTextBox: true, margin: 0,
  fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "Helped implement the simulator, the baselines and the experiment scripts", options: { bullet: true, breakLine: true } },
  { text: "Drafted and revised sections of the paper and this deck", options: { bullet: true, breakLine: true } },
  { text: "Checked the arithmetic in the result tables", options: { bullet: true } },
], { x: M + 0.3, y: 3.0, w: 5.1, h: 1.8, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 9, lineSpacing: 18 });

card(s, { x: 6.9, y: 2.45, w: 5.68, h: 3.1, name: "card-ai-me" });
s.addText("What I am responsible for", { x: 7.2, y: 2.58, w: 5.1, h: 0.35, isTextBox: true,
  margin: 0, fontSize: 15, bold: true, color: THEME.colors.dk2, fontFace: THEME.headFontFace });
s.addText([
  { text: "Every experiment was specified, dispatched and reviewed by me", options: { bullet: true, breakLine: true } },
  { text: "Every number was transcribed from a recorded run directory that names the run it came from", options: { bullet: true, breakLine: true } },
  { text: "The content and the claims", options: { bullet: true } },
], { x: 7.2, y: 3.0, w: 5.1, h: 1.8, isTextBox: true, margin: 0, fontSize: 13,
     color: THEME.colors.dk1, paraSpaceAfter: 9, lineSpacing: 18 });

plain(s, "The cost arithmetic behind the agent results is reproduced by a script in the repository rather than computed by hand, after it went wrong once by hand.", 5.9);
s.addText("", { placeholder: "source" });
s.addNotes(
  "Stated plainly because it is better said than discovered. The scoring script is " +
  "scripts/score_objective.py and the recorded tables are under results/recorded/.");

// ----------------------------------------------------------------- write

(async () => {
  await pres.writeFile({ fileName: "deck.pptx" });
  await applyTheme("deck.pptx", THEME);
  console.log("wrote deck.pptx");
})();

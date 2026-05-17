import React, { useState, useMemo } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    ReferenceArea, ReferenceLine
} from 'recharts';
import {
    Upload, FileText, Activity, Brain, AlertCircle,
    TrendingUp, TrendingDown, ChevronRight, ChevronDown, Calculator, Table, Search, Layers, Tag,
    ArrowUp, ArrowDown, X, GripVertical, Sparkles, BookOpen, Lock, Key, Stethoscope, Info, Hash, MapPin
} from 'lucide-react';

// --- Helper: Robust CSV Parser ---
const parseCSV = (text, filename) => {
    try {
        const cleanText = text.replace(/^\uFEFF/, '');
        const lines = cleanText.split(/\r\n|\n|\r/).filter(l => l.trim().length > 0);

        if (lines.length < 2) return null;

        const yearMatch = filename.match(/20\d{2}/);
        const year = yearMatch ? parseInt(yearMatch[0]) : 0;
        const label = year ? year.toString() : filename.split('.')[0];

        const headers = lines[0].split(',').map(h => h.replace(/["\r]/g, '').trim());

        const dataMap = {};
        let validRows = 0;

        for (let i = 1; i < lines.length; i++) {
            const rowRaw = lines[i].split(',');
            if (rowRaw.length < 2) continue;

            const rowClean = rowRaw.map(cell => cell.replace(/["\r]/g, '').trim());
            const segment = rowClean[0];

            if (segment && segment.length > 0) {
                const values = {};
                let hasData = false;

                headers.forEach((h, idx) => {
                    if (idx > 0 && h.length > 0 && rowClean[idx] !== undefined) {
                        const val = parseFloat(rowClean[idx]);
                        if (!isNaN(val)) {
                            values[h] = val;
                            hasData = true;
                        }
                    }
                });

                if (hasData) {
                    dataMap[segment] = values;
                    validRows++;
                }
            }
        }

        return {
            id: Math.random().toString(36).substr(2, 9),
            filename: filename,
            year: year,
            data: dataMap
        };
    } catch (error) {
        console.error("Error parsing CSV:", error);
        return null;
    }
};

// --- Helper: Stats Math ---
const calculateStats = (valuesRaw) => {
    const values = valuesRaw.filter(v => typeof v === 'number' && !isNaN(v));
    if (!values || values.length === 0) return null;

    const n = values.length;
    const sorted = [...values].sort((a, b) => a - b);
    const mean = values.reduce((a, b) => a + b, 0) / n;

    const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (n > 1 ? n - 1 : 1);
    const sd = Math.sqrt(variance);

    const mid = Math.floor(n / 2);
    const median = n % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    const q1 = sorted[Math.floor(n / 4)];
    const q3 = sorted[Math.floor(n * (3 / 4))];

    const abnormalCount = values.filter(v => Math.abs(v) > 1.96).length;
    const abnormalRate = (abnormalCount / n) * 100;

    return {
        n,
        mean: mean.toFixed(2),
        sd: sd.toFixed(2),
        median: median.toFixed(2),
        iqr: (q3 - q1).toFixed(2),
        min: sorted[0].toFixed(2),
        max: sorted[n - 1].toFixed(2),
        range: (sorted[n - 1] - sorted[0]).toFixed(2),
        abnormalRate: abnormalRate.toFixed(1) + '%'
    };
};

// --- ANATOMY MAPPING HELPER ---
// Maps Segment keywords (e.g., "1L") to likely Brodmann Areas for context
const ANATOMY_MAP = {
    '1L': { area: 'BA 10/46', name: 'L. Anterior Prefrontal' },
    '1R': { area: 'BA 10/46', name: 'R. Anterior Prefrontal' },
    '2L': { area: 'BA 8/9', name: 'L. Dorsolateral Prefrontal' },
    '2R': { area: 'BA 8/9', name: 'R. Dorsolateral Prefrontal' },
    '3L': { area: 'BA 3/1/2', name: 'L. Sensorimotor' },
    '3R': { area: 'BA 3/1/2', name: 'R. Sensorimotor' },
    '4L': { area: 'BA 17/18', name: 'L. Occipital (Visual)' },
    '4R': { area: 'BA 17/18', name: 'R. Occipital (Visual)' },
    'Tha': { area: 'Thalamus', name: 'Thalamocortical Loop' },
    'RedNuc': { area: 'Red Nucleus', name: 'Midbrain Teigmentum' },
    'SubTha': { area: 'Sub-Thalamus', name: 'Basal Ganglia Loop' }
};

const getAnatomy = (segmentName) => {
    for (const [key, info] of Object.entries(ANATOMY_MAP)) {
        if (segmentName.includes(key)) return info;
    }
    return { area: 'General', name: 'Cortex' };
};

// --- SYMPTOM ENGINE KNOWLEDGE BASE (Updated with ICD-10 & BAs) ---
const SYMPTOM_RULES = [
    {
        id: 'anxiety',
        name: "Anxiety / Hyper-arousal",
        icd: ["F41.1", "F41.9"],
        description: "Excessive Beta activity or Hyper-coherence in frontal/temporal loops.",
        relatedBAs: ["BA 10", "BA 46", "Amygdala Loop"],
        checks: [
            { band: 'HB', threshold: 1.5, type: 'high' },
            { band: 'B3', threshold: 1.5, type: 'high' },
            { band: 'A1', threshold: 2.0, type: 'high', segmentKeyword: 'Tha' }
        ]
    },
    {
        id: 'depression',
        name: "Mood Dysregulation / Depression",
        icd: ["F32.9", "F34.1"],
        description: "Frontal Alpha asymmetry or widespread Hypo-coherence.",
        relatedBAs: ["BA 9", "BA 24", "BA 32"],
        checks: [
            { band: 'A1', threshold: 1.5, type: 'high', segmentKeyword: '1L' },
            { band: 'D', threshold: -1.5, type: 'low' }
        ]
    },
    {
        id: 'attention',
        name: "Attention / Executive Function",
        icd: ["F90.0", "R41.84"],
        description: "Elevated Theta (slowing) or disconnected Beta in frontal regions.",
        relatedBAs: ["BA 10", "BA 11", "BA 46 (DLPFC)"],
        checks: [
            { band: 'T', threshold: 2.0, type: 'high', segmentKeyword: '1' },
            { band: 'D', threshold: 2.0, type: 'high' },
            { band: 'B1', threshold: -1.5, type: 'low' }
        ]
    },
    {
        id: 'pain',
        name: "Chronic Pain / Tension",
        icd: ["G89.2", "R52"],
        description: "Central/Parietal High Beta or Thalamic dysregulation.",
        relatedBAs: ["BA 1 (S1)", "BA 5/7 (Parietal)", "Thalamus"],
        checks: [
            { band: 'HB', threshold: 1.5, type: 'high', segmentKeyword: 'Tha' },
            { band: 'B3', threshold: 1.5, type: 'high' }
        ]
    },
    {
        id: 'trauma',
        name: "Trauma / PTSD Patterns",
        icd: ["F43.10", "F43.12"],
        description: "Temporal lobe instability or global hyper-coherence.",
        relatedBAs: ["BA 21 (Temporal)", "BA 38", "Hippocampus"],
        checks: [
            { band: 'T', threshold: 2.0, type: 'high', segmentKeyword: 'Tha' },
            { band: 'A2', threshold: -1.5, type: 'low' }
        ]
    }
];

const COLORS = ['#2563eb', '#db2777', '#ea580c', '#16a34a', '#9333ea', '#0891b2', '#ca8a04', '#475569'];

const App = () => {
    const [files, setFiles] = useState([]);
    const [segments, setSegments] = useState([]);
    const [bands, setBands] = useState([]);

    const [viewMode, setViewMode] = useState('analysis'); // 'analysis' or 'symptoms'
    const [selectedSegment, setSelectedSegment] = useState('');
    const [selectedBand, setSelectedBand] = useState('');
    const [labelMode, setLabelMode] = useState('set');
    const [selectedFileIndexForSymptoms, setSelectedFileIndexForSymptoms] = useState(0);
    const [isGlobalExpanded, setIsGlobalExpanded] = useState(false);

    const [loading, setLoading] = useState(false);
    const [userApiKey, setUserApiKey] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [aiReport, setAiReport] = useState(null);
    const [showKeyInput, setShowKeyInput] = useState(false);

    const handleFileUpload = async (e) => {
        setLoading(true);
        const uploadedFiles = Array.from(e.target.files);
        const processedData = [];

        for (const file of uploadedFiles) {
            try {
                const text = await file.text();
                const parsed = parseCSV(text, file.name);
                if (parsed && Object.keys(parsed.data).length > 0) {
                    processedData.push(parsed);
                }
            } catch (err) {
                console.error("File read error:", err);
            }
        }

        processedData.sort((a, b) => a.year - b.year);
        setFiles(prev => {
            const newFiles = [...prev, ...processedData];
            setSelectedFileIndexForSymptoms(newFiles.length - 1);
            return newFiles;
        });

        if (processedData.length > 0 && segments.length === 0) {
            const firstFile = processedData[0];
            const segKeys = Object.keys(firstFile.data);

            if (segKeys.length > 0) {
                const sampleSeg = firstFile.data[segKeys[0]];
                const bandKeys = Object.keys(sampleSeg);
                setSegments(segKeys);
                setBands(bandKeys);
                setSelectedSegment(segKeys[0]);
                setSelectedBand(bandKeys[0]);
            }
        }
        setLoading(false);
    };

    const moveFile = (index, direction) => {
        const newFiles = [...files];
        if (direction === 'up' && index > 0) {
            [newFiles[index], newFiles[index - 1]] = [newFiles[index - 1], newFiles[index]];
        } else if (direction === 'down' && index < newFiles.length - 1) {
            [newFiles[index], newFiles[index + 1]] = [newFiles[index + 1], newFiles[index]];
        }
        setFiles(newFiles);
    };

    const removeFile = (index) => setFiles(prev => prev.filter((_, i) => i !== index));

    // --- Analysis Logic ---
    const processedTrendData = useMemo(() => {
        if (files.length === 0) return [];
        return files.map((f, index) => {
            let nameLabel = f.filename;
            if (labelMode === 'year') nameLabel = f.year || 'Unknown';
            if (labelMode === 'set') nameLabel = `Set ${index + 1}`;

            if (selectedBand === 'ALL') {
                return { name: nameLabel, year: f.year, ...(f.data[selectedSegment] || {}) };
            }
            if (selectedSegment === 'GLOBAL_AVG') {
                const vals = Object.values(f.data).map(s => s[selectedBand]).filter(v => !isNaN(v));
                const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
                return { name: nameLabel, year: f.year, value: avg, isAbnormal: avg && Math.abs(avg) > 1.5 };
            }
            const val = f.data[selectedSegment]?.[selectedBand];
            return { name: nameLabel, year: f.year, value: val, isAbnormal: val && Math.abs(val) > 1.96 };
        });
    }, [files, selectedSegment, selectedBand, labelMode]);

    const tableData = useMemo(() => {
        if (files.length === 0) return [];
        let rows = [];

        if (selectedBand === 'ALL') {
            rows = bands.map(band => ({
                label: band,
                type: 'band',
                values: files.map(f => f.data[selectedSegment]?.[band])
            }));
        } else if (selectedSegment === 'GLOBAL_AVG') {
            const globalValues = files.map(f => {
                const vals = Object.values(f.data).map(s => s[selectedBand]).filter(v => !isNaN(v));
                return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
            });
            rows.push({ label: 'GLOBAL AVERAGE', type: 'main', isExpandable: true, values: globalValues });
            if (isGlobalExpanded) {
                segments.forEach(seg => {
                    rows.push({ label: seg, type: 'sub', values: files.map(f => f.data[seg]?.[selectedBand]) });
                });
            }
        } else {
            rows.push({ label: selectedSegment, type: 'main', values: files.map(f => f.data[selectedSegment]?.[selectedBand]) });
        }
        return rows.map(row => ({ ...row, stats: calculateStats(row.values) }));
    }, [files, selectedBand, selectedSegment, bands, segments, isGlobalExpanded]);

    // --- Symptom Logic with Anatomy ---
    const symptomAnalysis = useMemo(() => {
        if (files.length === 0 || selectedFileIndexForSymptoms < 0) return [];
        const targetFile = files[selectedFileIndexForSymptoms];
        const analysis = SYMPTOM_RULES.map(rule => {
            let maxSeverity = 0;
            let contributors = [];
            Object.entries(targetFile.data).forEach(([segName, segValues]) => {
                rule.checks.forEach(check => {
                    if (check.segmentKeyword && !segName.includes(check.segmentKeyword)) return;
                    const val = segValues[check.band];
                    if (val === undefined || isNaN(val)) return;
                    let severity = 0, triggered = false;
                    if (check.type === 'high' && val > check.threshold) {
                        severity = Math.min(10, Math.max(1, ((val - check.threshold) / 1.5) * 10));
                        triggered = true;
                    } else if (check.type === 'low' && val < -check.threshold) {
                        severity = Math.min(10, Math.max(1, ((Math.abs(val) - check.threshold) / 1.5) * 10));
                        triggered = true;
                    }
                    if (triggered) {
                        if (severity > maxSeverity) maxSeverity = severity;
                        // Enrich contributor with Anatomy Info
                        const anatomy = getAnatomy(segName);
                        contributors.push({
                            segment: segName,
                            band: check.band,
                            value: val,
                            severity: severity,
                            anatomy: anatomy
                        });
                    }
                });
            });
            contributors.sort((a, b) => b.severity - a.severity);
            return { ...rule, score: maxSeverity, contributors: contributors.slice(0, 5) };
        });
        return analysis.sort((a, b) => b.score - a.score);
    }, [files, selectedFileIndexForSymptoms]);

    // --- AI Generation ---
    const generateReport = async () => {
        if (!userApiKey) { setShowKeyInput(true); return; }
        setIsGenerating(true);
        setAiReport(null);

        let promptText = "";
        if (viewMode === 'analysis') {
            const dataSummary = tableData.slice(0, 10).map(row => `${row.label}: Mean=${row.stats?.mean}, Trend=[${row.values.map(v => v?.toFixed(2)).join(', ')}]`).join('\n');
            promptText = `Clinical Interpretation for QEEG Trend.\nScope: ${selectedSegment} (${selectedBand}).\n\nData Summary:\n${dataSummary}\n\nProvide a clinical assessment.`;
        } else {
            const topSymptoms = symptomAnalysis.filter(s => s.score > 2).slice(0, 3);
            const sympDesc = topSymptoms.map(s =>
                `${s.name} (ICD: ${s.icd.join(', ')}) - Severity ${s.score.toFixed(1)}/10. Drivers: ${s.contributors.map(c => `${c.anatomy.area} (${c.segment})`).join(', ')}`
            ).join('\n');
            promptText = `QEEG Symptom Correlation & ICD Coding.\nDetected Patterns:\n${sympDesc}\n\nCorrelate these findings with specific Brodmann Areas and medical literature. Suggest ICD-10 codes if appropriate.`;
        }

        try {
            const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key=${userApiKey}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contents: [{ parts: [{ text: promptText }] }],
                    tools: [{ google_search: {} }]
                })
            });
            const data = await response.json();
            const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
            const grounding = data.candidates?.[0]?.groundingMetadata;
            setAiReport({ text, grounding });
        } catch (error) {
            alert(error.message);
        } finally {
            setIsGenerating(false);
        }
    };

    const renderReportText = (text) => {
        if (!text) return null;
        return text.split('\n').map((line, i) => (
            <p key={i} className={`mb-2 ${line.startsWith('**') ? 'font-bold text-slate-800 mt-4' : 'text-slate-600'}`}>{line.replace(/\*\*/g, '')}</p>
        ));
    };

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900 font-sans p-4 md:p-8">

            {/* Header */}
            <header className="max-w-7xl mx-auto mb-6 flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-200 pb-6">
                <div>
                    <h1 className="text-3xl font-bold text-slate-800 flex items-center gap-3">
                        <Brain className="w-8 h-8 text-blue-600" />
                        NeuroTrack <span className="text-slate-400 font-light">Suite</span>
                    </h1>
                    <p className="text-slate-500 mt-2">Longitudinal QEEG Analysis & Clinical Symptom Matching</p>
                </div>

                <div className="mt-4 md:mt-0 flex flex-col items-end gap-2">
                    <label className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-md cursor-pointer transition-colors">
                        <Upload className="w-4 h-4" />
                        <span className="font-medium">{loading ? 'Processing...' : 'Load CSV Sets'}</span>
                        <input type="file" multiple accept=".csv" onChange={handleFileUpload} className="hidden" />
                    </label>
                </div>
            </header>

            {files.length === 0 ? (
                <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm border-2 border-dashed border-slate-300 p-12 text-center">
                    <Activity className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <h3 className="text-xl font-semibold text-slate-700">No Data Loaded</h3>
                    <p className="text-slate-500 mt-2 mb-6">Upload your longitudinal CSV files to begin.</p>
                </div>
            ) : (
                <div className="max-w-7xl mx-auto">

                    {/* Tabs */}
                    <div className="flex gap-4 mb-6 border-b border-slate-200">
                        <button onClick={() => setViewMode('analysis')} className={`pb-3 px-2 font-medium text-sm flex items-center gap-2 transition-colors ${viewMode === 'analysis' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-slate-500 hover:text-slate-700'}`}>
                            <Activity className="w-4 h-4" /> Data Analysis
                        </button>
                        <button onClick={() => setViewMode('symptoms')} className={`pb-3 px-2 font-medium text-sm flex items-center gap-2 transition-colors ${viewMode === 'symptoms' ? 'border-b-2 border-emerald-600 text-emerald-600' : 'text-slate-500 hover:text-slate-700'}`}>
                            <Stethoscope className="w-4 h-4" /> Symptom Matcher
                        </button>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                        {/* SIDEBAR */}
                        <div className="lg:col-span-3 space-y-6">
                            {viewMode === 'analysis' ? (
                                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                                    <div className="flex items-center gap-2 mb-4 text-slate-400"><Layers className="w-4 h-4" /><h3 className="text-sm font-bold uppercase tracking-wider">Analysis Scope</h3></div>
                                    <div className="mb-4">
                                        <label className="block text-sm font-medium text-slate-700 mb-1">Frequency Band</label>
                                        <select value={selectedBand} onChange={(e) => setSelectedBand(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none font-medium text-slate-700">
                                            <option value="ALL" className="font-bold text-blue-600">✦ All Bands (Matrix View)</option>
                                            <optgroup label="Individual Bands">{bands.map(b => <option key={b} value={b}>{b}</option>)}</optgroup>
                                        </select>
                                    </div>
                                    <div className="mb-4">
                                        <label className="block text-sm font-medium text-slate-700 mb-1">Segment</label>
                                        <div className="relative">
                                            <select value={selectedSegment} onChange={(e) => { setSelectedSegment(e.target.value); setIsGlobalExpanded(false); }} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none appearance-none font-medium text-slate-700">
                                                <option value="GLOBAL_AVG" className="font-bold text-blue-600">✦ Global Average</option>
                                                <optgroup label="Segments">{segments.map(s => <option key={s} value={s}>{s}</option>)}</optgroup>
                                            </select>
                                            <div className="absolute right-3 top-2.5 pointer-events-none text-slate-400"><ChevronRight className="w-4 h-4 rotate-90" /></div>
                                        </div>
                                    </div>
                                    <div className="pt-4 border-t border-slate-100">
                                        <div className="flex items-center gap-2 mb-2 text-slate-400"><Tag className="w-4 h-4" /><h3 className="text-xs font-bold uppercase tracking-wider">Label Style</h3></div>
                                        <div className="flex bg-slate-100 p-1 rounded-lg">
                                            {['year', 'set', 'filename'].map(mode => (
                                                <button key={mode} onClick={() => setLabelMode(mode)} className={`flex-1 py-1 text-xs font-medium rounded-md capitalize transition-all ${labelMode === mode ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>{mode}</button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                                    <div className="flex items-center gap-2 mb-4 text-slate-400"><Stethoscope className="w-4 h-4" /><h3 className="text-sm font-bold uppercase tracking-wider">Symptom Target</h3></div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Analyze File (Set)</label>
                                    <select value={selectedFileIndexForSymptoms} onChange={(e) => setSelectedFileIndexForSymptoms(parseInt(e.target.value))} className="w-full bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-emerald-500 outline-none font-medium text-emerald-800">
                                        {files.map((f, i) => <option key={f.id} value={i}>Set {i + 1}: {f.filename} ({f.year || 'N/A'})</option>)}
                                    </select>
                                </div>
                            )}

                            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                                <div className="flex items-center gap-2 mb-4 text-slate-400"><GripVertical className="w-4 h-4" /><h3 className="text-sm font-bold uppercase tracking-wider">Timeline</h3></div>
                                <div className="space-y-2 max-h-60 overflow-y-auto">
                                    {files.map((file, idx) => (
                                        <div key={file.id} className="flex items-center justify-between bg-slate-50 p-2 rounded border border-slate-100">
                                            <div className="flex items-center gap-2 overflow-hidden">
                                                <span className="text-xs font-bold bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">Set {idx + 1}</span>
                                                <span className="text-xs text-slate-600 truncate max-w-[100px]">{file.filename}</span>
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <button onClick={() => moveFile(idx, 'up')} disabled={idx === 0} className="p-1 text-slate-400 hover:text-blue-600 disabled:opacity-30"><ArrowUp className="w-3 h-3" /></button>
                                                <button onClick={() => moveFile(idx, 'down')} disabled={idx === files.length - 1} className="p-1 text-slate-400 hover:text-blue-600 disabled:opacity-30"><ArrowDown className="w-3 h-3" /></button>
                                                <button onClick={() => removeFile(idx)} className="p-1 text-slate-400 hover:text-red-600 ml-1"><X className="w-3 h-3" /></button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* MAIN CONTENT */}
                        <div className="lg:col-span-9 space-y-6">

                            {/* 1. GRAPH VIEW (Analysis Only) */}
                            {viewMode === 'analysis' && (
                                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                                    <div className="flex justify-between items-center mb-6">
                                        <h2 className="text-lg font-semibold text-slate-800">
                                            Trajectory: <span className="text-blue-600">{selectedSegment === 'GLOBAL_AVG' ? 'Global Brain Average' : selectedSegment}</span> ({selectedBand === 'ALL' ? 'All Bands' : selectedBand})
                                        </h2>
                                        {selectedBand !== 'ALL' && (
                                            <div className="flex items-center gap-2 text-sm text-slate-500">
                                                <span className="flex items-center gap-1"><div className="w-3 h-3 bg-red-100 border border-red-300 rounded-sm"></div> Deviation Zone ({'>'}1.96 SD)</span>
                                            </div>
                                        )}
                                    </div>
                                    <div className="h-80 w-full relative">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={processedTrendData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                                <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 12 }} />
                                                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} domain={['auto', 'auto']} />
                                                <Tooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} labelStyle={{ color: '#64748b', marginBottom: '0.5rem' }} />
                                                <Legend />
                                                {selectedBand === 'ALL' ? (
                                                    bands.map((band, idx) => <Line key={band} connectNulls type="monotone" dataKey={band} stroke={COLORS[idx % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 6 }} />)
                                                ) : (
                                                    <>
                                                        <ReferenceArea y1={1.96} y2={10} fill="red" fillOpacity={0.05} stroke="none" />
                                                        <ReferenceArea y1={-1.96} y2={-10} fill="red" fillOpacity={0.05} stroke="none" />
                                                        <ReferenceLine y={0} stroke="#cbd5e1" />
                                                        <Line connectNulls type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={3} activeDot={{ r: 8 }} dot={{ r: 4, strokeWidth: 2, fill: "white" }} name="Coherence/Value" />
                                                    </>
                                                )}
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* 2. DATA MATRIX TABLE (New Pivoted Layout) */}
                            {viewMode === 'analysis' && (
                                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 overflow-hidden">
                                    <div className="flex items-center justify-between mb-4">
                                        <div className="flex items-center gap-2">
                                            <Table className="w-5 h-5 text-indigo-600" />
                                            <h3 className="font-semibold text-slate-800">Statistical Matrix</h3>
                                        </div>
                                    </div>

                                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                                        <table className="w-full text-sm text-left">
                                            <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-200">
                                                <tr>
                                                    <th className="px-4 py-3 font-bold bg-slate-100 sticky left-0 z-10 border-r border-slate-200 min-w-[200px]">
                                                        {selectedBand === 'ALL' ? 'Frequency Band' : 'Segment'}
                                                    </th>

                                                    {/* Set Columns */}
                                                    {files.map((f, i) => (
                                                        <th key={f.id} className="px-4 py-3 font-semibold text-blue-700 bg-blue-50/50 border-r border-slate-100 min-w-[100px]">
                                                            {labelMode === 'set' ? `Set ${i + 1}` : (labelMode === 'year' ? f.year : f.filename.slice(0, 10))}
                                                        </th>
                                                    ))}

                                                    {/* Stats Columns */}
                                                    <th className="px-4 py-3 bg-slate-100 text-slate-600 border-l border-slate-200">Mean</th>
                                                    <th className="px-4 py-3 bg-slate-100 text-slate-600">SD</th>
                                                    <th className="px-4 py-3 bg-slate-100 text-slate-600">Median</th>
                                                    <th className="px-4 py-3 bg-slate-100 text-slate-600">IQR</th>
                                                    <th className="px-4 py-3 bg-slate-100 text-slate-600">% Abn</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {tableData.map((row, idx) => (
                                                    <React.Fragment key={idx}>
                                                        <tr className={`hover:bg-slate-50 ${row.type === 'main' ? 'bg-slate-50/80 font-medium' : ''} ${row.type === 'sub' ? 'text-xs' : ''}`}>
                                                            <td className="px-4 py-2 font-medium text-slate-700 bg-white sticky left-0 z-10 border-r border-slate-100 flex items-center gap-2">
                                                                {row.isExpandable && (
                                                                    <button onClick={() => setIsGlobalExpanded(!isGlobalExpanded)} className="p-1 hover:bg-slate-100 rounded">
                                                                        {isGlobalExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                                                    </button>
                                                                )}
                                                                {row.type === 'sub' && <span className="w-4" />}
                                                                {row.label}
                                                            </td>

                                                            {/* Values Per Set */}
                                                            {row.values.map((val, vIdx) => (
                                                                <td key={vIdx} className="px-4 py-2 border-r border-slate-50 text-slate-600">
                                                                    {val !== undefined && val !== null ? (
                                                                        <span className={Math.abs(val) > 1.96 ? 'text-red-600 font-bold' : ''}>
                                                                            {val.toFixed(2)}
                                                                        </span>
                                                                    ) : <span className="text-slate-300">-</span>}
                                                                </td>
                                                            ))}

                                                            {/* Stats */}
                                                            <td className="px-4 py-2 bg-slate-50/30 border-l border-slate-100 font-mono text-xs">{row.stats?.mean}</td>
                                                            <td className="px-4 py-2 bg-slate-50/30 font-mono text-xs">{row.stats?.sd}</td>
                                                            <td className="px-4 py-2 bg-slate-50/30 font-mono text-xs">{row.stats?.median}</td>
                                                            <td className="px-4 py-2 bg-slate-50/30 font-mono text-xs">{row.stats?.iqr}</td>
                                                            <td className={`px-4 py-2 bg-slate-50/30 font-mono text-xs font-bold ${parseInt(row.stats?.abnormalRate) > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                                                {row.stats?.abnormalRate}
                                                            </td>
                                                        </tr>
                                                    </React.Fragment>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}

                            {/* 3. SYMPTOM VIEW */}
                            {viewMode === 'symptoms' && (
                                <div className="space-y-6">
                                    <div className="bg-gradient-to-r from-emerald-500 to-teal-600 rounded-xl shadow-md p-6 text-white">
                                        <h2 className="text-xl font-bold flex items-center gap-2"><Brain className="w-6 h-6" /> Symptom Probability Engine</h2>
                                        <p className="opacity-90 mt-1 text-sm">Analyzing Set {selectedFileIndexForSymptoms + 1} for neurological patterns derived from Z-score deviations.</p>
                                    </div>
                                    <div className="grid gap-4">
                                        {symptomAnalysis.map(symptom => (
                                            <div key={symptom.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden transition-all hover:shadow-md">
                                                <div className="p-5 flex flex-col md:flex-row gap-4 md:items-center justify-between">
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <h3 className="font-bold text-slate-800 text-lg">{symptom.name}</h3>
                                                            {symptom.score > 7 && <span className="bg-red-100 text-red-700 text-xs font-bold px-2 py-1 rounded">HIGH PROBABILITY</span>}
                                                        </div>

                                                        {/* ICD CODES */}
                                                        <div className="flex items-center gap-2 mb-3">
                                                            <Hash className="w-3 h-3 text-slate-400" />
                                                            {symptom.icd.map(code => (
                                                                <span key={code} className="bg-slate-100 text-slate-600 text-xs px-2 py-0.5 rounded border border-slate-200 font-mono">{code}</span>
                                                            ))}
                                                        </div>

                                                        <p className="text-slate-500 text-sm">{symptom.description}</p>
                                                    </div>

                                                    {/* Severity Bar */}
                                                    <div className="w-full md:w-1/3">
                                                        <div className="flex justify-between text-xs mb-1 font-semibold">
                                                            <span className="text-slate-400">Severity</span>
                                                            <span className={symptom.score > 5 ? 'text-red-600' : 'text-emerald-600'}>{symptom.score.toFixed(1)} / 10</span>
                                                        </div>
                                                        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                                                            <div className={`h-full rounded-full transition-all duration-1000 ${symptom.score > 7 ? 'bg-red-500' : symptom.score > 4 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${symptom.score * 10}%` }} />
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Expansion: Source Generators */}
                                                {symptom.contributors.length > 0 && (
                                                    <div className="bg-slate-50 p-4 border-t border-slate-100 text-sm">
                                                        <div className="flex items-center gap-2 mb-3">
                                                            <MapPin className="w-4 h-4 text-blue-500" />
                                                            <p className="font-semibold text-slate-600 text-xs uppercase tracking-wider">Source Neural Generators (Brodmann Areas)</p>
                                                        </div>

                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                            {symptom.contributors.map((c, idx) => (
                                                                <div key={idx} className="flex items-center gap-3 bg-white p-2 rounded border border-slate-200 shadow-sm">
                                                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${c.value > 0 ? 'bg-red-400' : 'bg-blue-400'}`} />

                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="flex justify-between items-center">
                                                                            <span className="font-bold text-slate-700 text-xs truncate" title={c.anatomy.name}>{c.anatomy.area}</span>
                                                                            <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">Z: {c.value.toFixed(2)}</span>
                                                                        </div>
                                                                        <div className="flex justify-between items-center text-xs text-slate-400 mt-0.5">
                                                                            <span className="truncate">{c.anatomy.name}</span>
                                                                            <span className="font-mono">{c.band} @ {c.segment}</span>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* AI Report */}
                            <div className="bg-white rounded-xl shadow-sm border border-blue-100 overflow-hidden">
                                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-4 flex justify-between items-center border-b border-blue-100">
                                    <div className="flex items-center gap-2">
                                        <Sparkles className="w-5 h-5 text-blue-600" />
                                        <h3 className="font-bold text-blue-900">Neurologist's AI Assistant</h3>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {showKeyInput ? (
                                            <div className="flex items-center gap-2 bg-white rounded-full px-3 py-1 border border-blue-200 shadow-sm"><Key className="w-3 h-3 text-slate-400" /><input type="password" placeholder="Enter Google API Key" value={userApiKey} onChange={(e) => setUserApiKey(e.target.value)} className="text-xs outline-none w-40 text-slate-600" /></div>
                                        ) : (
                                            <button onClick={() => setShowKeyInput(true)} className="text-xs text-blue-400 hover:text-blue-600 flex items-center gap-1"><Lock className="w-3 h-3" /> Set API Key</button>
                                        )}
                                        <button onClick={generateReport} disabled={isGenerating} className={`px-4 py-2 rounded-lg text-sm font-medium text-white flex items-center gap-2 shadow-sm transition-all ${isGenerating ? 'bg-slate-300 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700'}`}>
                                            {isGenerating ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <><Sparkles className="w-4 h-4" /> Generate Report</>}
                                        </button>
                                    </div>
                                </div>
                                <div className="p-6">
                                    {aiReport ? (
                                        <div className="animate-fadeIn">
                                            <div className="prose prose-sm max-w-none text-slate-700">{renderReportText(aiReport.text)}</div>
                                            {aiReport.grounding?.groundingChunks && (
                                                <div className="mt-6 pt-4 border-t border-slate-100">
                                                    <div className="grid gap-2">{aiReport.grounding.groundingChunks.map((chunk, idx) => chunk.web ? <a key={idx} href={chunk.web.uri} target="_blank" rel="noopener noreferrer" className="block bg-slate-50 hover:bg-slate-100 p-2 rounded border border-slate-100 text-xs text-blue-600 truncate">{chunk.web.title}</a> : null)}</div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="text-center text-slate-400 py-8"><p>Generate a clinical report based on the currently viewed data.</p></div>
                                    )}
                                </div>
                            </div>

                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default App;
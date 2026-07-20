// Vendored from presentation-learn-phantom-update (kim-overlay); keep maths in sync.
// Plotly module wrapper. We use the prebuilt "basic" minified bundle (scatter
// is all we need) and create the React component via react-plotly.js's factory
// so the heavy Plotly dependency is imported exactly once and code-split into
// its own chunk (see vite.config.ts manualChunks).
import Plotly from 'plotly.js-basic-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

export const Plot = createPlotlyComponent(Plotly);
export default Plotly;

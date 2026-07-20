// Vendored from presentation-learn-phantom-update (kim-overlay); keep maths in sync.
// The basic Plotly bundle and the react-plotly.js factory entry point ship
// without their own type declarations. We only need loose typings here; the
// Vite build transpiles without type-checking, these keep the editor quiet.
declare module 'plotly.js-basic-dist-min' {
  const Plotly: any;
  export default Plotly;
}

declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react';
  const createPlotlyComponent: (plotly: any) => ComponentType<any>;
  export default createPlotlyComponent;
}

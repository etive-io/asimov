import mermaid from 'mermaid';
import elkLayouts from '@mermaid-js/layout-elk';

mermaid.registerLayoutLoaders(elkLayouts);

mermaid.initialize({
  startOnLoad: false,      // we call mermaid.render() manually after page load
  securityLevel: 'antiscript',
  flowchart: {
    defaultRenderer: 'elk',
  },
  theme: 'base',
  themeVariables: {
    primaryTextColor: '#24292e',
    lineColor: '#586069',
  },
});

window.mermaid = mermaid;

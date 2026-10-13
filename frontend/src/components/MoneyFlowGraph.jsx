import { useEffect, useRef } from 'react';
import { Network } from 'vis-network/standalone';
import { DataSet } from 'vis-data';

/**
 * Renders the money-flow graph returned by the NetworkX service.
 * This component performs NO graph analysis — it only draws nodes/edges and
 * forwards clicks. Cycles, scores and suspicious flags all come from the API.
 */
export default function MoneyFlowGraph({ payload, onSelectNode, onSelectEdge }) {
  const ref = useRef(null);
  const networkRef = useRef(null);

  useEffect(() => {
    if (!ref.current || !payload) return undefined;

    const nodes = (payload.nodes || []).map((n) => {
      const anomaly = n.anomaly_count > 0;
      const risk = n.fraud_risk || 0;
      const color = anomaly
        ? { background: '#f0b429', border: '#f7cd6a' }
        : risk >= 81
          ? { background: '#ff4d6d', border: '#ff8fa5' }
          : risk >= 61
            ? { background: '#ff7a45', border: '#ffab8a' }
            : n.entity_type === 'business'
              ? { background: '#8a5cff', border: '#b79bff' }
              : { background: '#4f8cff', border: '#9dbfff' };

      return {
        id: n.id,
        label: n.label,
        title: `<b>${n.label}</b><br/>role: ${n.role}<br/>in: ₹${Math.round(
          n.in_total,
        ).toLocaleString('en-IN')}<br/>out: ₹${Math.round(
          n.out_total,
        ).toLocaleString('en-IN')}<br/>txns: ${n.tx_count}<br/>fraud risk: ${n.fraud_risk}`,
        shape: n.entity_type === 'business' ? 'box' : 'dot',
        size: 12 + Math.min(22, Math.log10((n.in_total || 0) + (n.out_total || 0) + 1) * 4),
        color,
        font: { color: '#e8edf7', size: 11 },
        borderWidth: n.selected ? 3 : 1,
      };
    });

    const edges = (payload.edges || []).map((e) => ({
      id: e.id,
      from: e.source,
      to: e.target,
      arrows: 'to',
      width: 0.6 + Math.min(4, Math.log10((e.amount || 1) + 1) * 0.7),
      color: e.in_suspicious_cycle
        ? { color: '#ff4d6d', highlight: '#ff8fa5' }
        : e.max_fraud_score >= 61
          ? { color: '#ff7a45', highlight: '#ffab8a' }
          : { color: '#3a4a68', highlight: '#4f8cff' },
      dashes: e.in_suspicious_cycle ? [4, 4] : false,
      title: `${e.count} txn(s)<br/>₹${Math.round(e.amount).toLocaleString('en-IN')}<br/>max fraud score: ${e.max_fraud_score}${
        e.in_suspicious_cycle ? '<br/><b>part of a suspicious cycle</b>' : ''
      }`,
    }));

    const data = { nodes: new DataSet(nodes), edges: new DataSet(edges) };
    const options = {
      physics: {
        stabilization: { iterations: 180, updateInterval: 25 },
        barnesHut: { gravitationalConstant: -9000, springLength: 130, springConstant: 0.04, damping: 0.5 },
      },
      interaction: { hover: true, tooltipDelay: 120, navigationButtons: true, keyboard: false },
      nodes: { borderWidth: 1 },
      edges: { smooth: { type: 'continuous' } },
    };

    const network = new Network(ref.current, data, options);
    networkRef.current = network;

    network.on('selectNode', (params) => {
      if (onSelectNode && params.nodes.length) onSelectNode(params.nodes[0]);
    });
    network.on('selectEdge', (params) => {
      if (onSelectEdge && params.edges.length) {
        const found = (payload.edges || []).find((e) => e.id === params.edges[0]);
        if (found) onSelectEdge(found);
      }
    });
    network.once('stabilizationIterationsDone', () => {
      network.fit({ animation: { duration: 500 } });
    });

    return () => {
      network.destroy();
      networkRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload]);

  return <div className="graph-canvas" ref={ref} />;
}

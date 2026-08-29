import { useMemo, useEffect } from "react";
import { ReactFlow, Background, Controls, MarkerType, useReactFlow } from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "./nodes";

const NODE_W = 240;
const NODE_H = 92;

function layout(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 70, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

function FitOnChange({ count }) {
  const rf = useReactFlow();
  useEffect(() => {
    const id = setTimeout(() => {
      try { rf.fitView({ padding: 0.2, duration: 400 }); } catch (e) {}
    }, 80);
    return () => clearTimeout(id);
  }, [count, rf]);
  return null;
}

export default function MissionGraph({ mission, tasks }) {
  const { nodes, edges } = useMemo(() => {
    const ns = [];
    const es = [];

    ns.push({ id: "manager", type: "hive", data: { kind: "manager" }, position: { x: 0, y: 0 } });

    const activeEdge = (status) =>
      status === "running" || status === "needs_revision";

    tasks.forEach((t) => {
      ns.push({
        id: t.id,
        type: "hive",
        data: {
          kind: "task",
          title: t.title,
          subtitle: t.owner_role,
          status: t.status,
          revising: t.status === "running" && t.retry_count > 0,
        },
        position: { x: 0, y: 0 },
      });
      if (!t.dependencies || t.dependencies.length === 0) {
        es.push({ id: `m-${t.id}`, source: "manager", target: t.id });
      }
      (t.dependencies || []).forEach((d) => {
        es.push({ id: `${d}-${t.id}`, source: d, target: t.id, animated: activeEdge(t.status) });
      });
    });

    // leaf tasks -> review
    const hasDependents = new Set();
    tasks.forEach((t) => (t.dependencies || []).forEach((d) => hasDependents.add(d)));
    const leaves = tasks.filter((t) => !hasDependents.has(t.id));
    if (tasks.length > 0) {
      ns.push({ id: "review", type: "hive", data: { kind: "review" }, position: { x: 0, y: 0 } });
      leaves.forEach((l) => es.push({ id: `${l.id}-review`, source: l.id, target: "review" }));
      ns.push({
        id: "verified",
        type: "hive",
        data: { kind: "verified", status: mission?.status === "verified" ? "verified" : "pending" },
        position: { x: 0, y: 0 },
      });
      es.push({
        id: "review-verified",
        source: "review",
        target: "verified",
        animated: mission?.status === "reviewing",
      });
    }

    const styled = es.map((e) => ({
      ...e,
      markerEnd: { type: MarkerType.ArrowClosed, color: e.animated ? "#38bdf8" : "#3f3f46", width: 16, height: 16 },
      style: { stroke: e.animated ? "#38bdf8" : "#3f3f46", strokeWidth: 1.5 },
    }));

    return { nodes: layout(ns, styled), edges: styled };
  }, [mission, tasks]);

  return (
    <div className="w-full h-full" data-testid="mission-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.3}
      >
        <FitOnChange count={nodes.length} />
        <Background color="#27272a" gap={22} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

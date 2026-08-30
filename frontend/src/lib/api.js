import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const createMission = (goal) =>
  axios.post(`${API}/missions`, { goal }).then((r) => r.data);
export const getMission = (id) =>
  axios.get(`${API}/missions/${id}`).then((r) => r.data);
export const getWorkerDetail = (mid, aid) =>
  axios.get(`${API}/missions/${mid}/agents/${aid}`).then((r) => r.data);
export const listMissions = (projectId) =>
  axios.get(`${API}/missions${projectId ? `?project_id=${projectId}` : ""}`).then((r) => r.data);
export const getCredits = () =>
  axios.get(`${API}/credits`).then((r) => r.data);
export const renewCredits = () =>
  axios.post(`${API}/credits/renew`).then((r) => r.data);
export const getPlans = () =>
  axios.get(`${API}/plans`).then((r) => r.data);
export const razorpayConfig = () =>
  axios.get(`${API}/razorpay/config`).then((r) => r.data);
export const createOrder = (plan, billing) =>
  axios.post(`${API}/create-order`, { plan, billing }).then((r) => r.data);
export const verifyPayment = (payload) =>
  axios.post(`${API}/verify-payment`, payload).then((r) => r.data);
export const listProjects = () =>
  axios.get(`${API}/projects`).then((r) => r.data);
export const getWorkforce = () =>
  axios.get(`${API}/workforce`).then((r) => r.data);
export const getExamples = () =>
  axios.get(`${API}/examples`).then((r) => r.data);

// ---- HIVE Local Runner ----
export const runnerPair = () =>
  axios.post(`${API}/runner/pair`).then((r) => r.data);
export const runnerSession = (sid) =>
  axios.get(`${API}/runner/session/${sid}`).then((r) => r.data);
export const runnerApprove = (sid) =>
  axios.post(`${API}/runner/session/${sid}/approve`).then((r) => r.data);
export const runnerTree = (sid) =>
  axios.get(`${API}/runner/session/${sid}/tree`).then((r) => r.data);
export const runnerSeedDemo = (sid) =>
  axios.post(`${API}/runner/session/${sid}/seed-demo`).then((r) => r.data);
export const runnerDebug = () =>
  axios.get(`${API}/runner/debug`).then((r) => r.data);
export const createLocalMission = (session_id, goal) =>
  axios.post(`${API}/missions/local`, { session_id, goal: goal || "Organize and prepare this project." }).then((r) => r.data);

export const runnerWsUrl = () =>
  `${API.replace(/^http/, "ws")}/runner/ws`;

export { API };

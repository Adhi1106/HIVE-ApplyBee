import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const createMission = (goal) =>
  axios.post(`${API}/missions`, { goal }).then((r) => r.data);
export const getMission = (id) =>
  axios.get(`${API}/missions/${id}`).then((r) => r.data);
export const listMissions = () =>
  axios.get(`${API}/missions`).then((r) => r.data);
export const getCredits = () =>
  axios.get(`${API}/credits`).then((r) => r.data);
export const getWorkforce = () =>
  axios.get(`${API}/workforce`).then((r) => r.data);
export const getExamples = () =>
  axios.get(`${API}/examples`).then((r) => r.data);

export { API };

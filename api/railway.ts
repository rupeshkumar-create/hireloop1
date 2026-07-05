import { defineRailway, project, service } from "railway/iac";

export default defineRailway(() => {
  const hireloop1 = service("hireloop1", {});

  return project("truthful-forgiveness", {
    resources: [hireloop1],
  });
});

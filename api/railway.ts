import { defineRailway, project, service } from "railway/iac";

export default defineRailway(() => {
  return project("hireschema-api", {
    resources: [
      service("hireloop1", {
        build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
        deploy: {
          healthcheckPath: "/api/v1/health",
          healthcheckTimeout: 120,
          multiRegionConfig: {
            "asia-southeast1-eqsg3a": { numReplicas: 1 },
          },
          restartPolicyType: "ON_FAILURE",
          restartPolicyMaxRetries: 5,
        },
      }),
    ],
  });
});

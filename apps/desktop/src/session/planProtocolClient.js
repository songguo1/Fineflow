import {
  approvePlan,
  createPlan,
  getPlan,
  listPlans,
  patchPlan,
  rejectPlan,
  runPlan,
} from "../api/apiClient.js";

export function createPlanProtocolClient(baseUrl) {
  return {
    createPlanDraft(request) {
      return createPlan(baseUrl, request);
    },
    loadPlanDraft(planId) {
      return getPlan(baseUrl, planId);
    },
    listPlanDrafts(options) {
      return listPlans(baseUrl, options);
    },
    patchPlanDraft(planId, patch) {
      return patchPlan(baseUrl, planId, patch);
    },
    approvePlanDraft(planId) {
      return approvePlan(baseUrl, planId);
    },
    rejectPlanDraft(planId) {
      return rejectPlan(baseUrl, planId);
    },
    runPlanDraft(planId, request = null) {
      return runPlan(baseUrl, planId, request);
    },
  };
}

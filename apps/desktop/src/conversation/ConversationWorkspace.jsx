import { ClipboardList } from "lucide-react";

import { PanelTitle } from "../layout/LayoutPrimitives.jsx";
import { ChatTranscript } from "./ChatTranscript.jsx";
import { ConversationComposer } from "./ConversationComposer.jsx";
import { ResumePanel } from "./ResumePanel.jsx";
import { PlanDraftCard } from "../planning/PlanDraftCard.jsx";

export function ConversationWorkspace({
  ui,
  llmSettings,
  sessionId,
  transcript,
  runState,
  pendingTask,
  activeIssue,
  activeRisk,
  repair,
  planDraft,
  planningBusy,
  planMode,
  allowedActions,
  hasPendingInteraction,
  resumeMode,
  setResumeMode,
  resumePatch,
  resumeFields,
  missingSlots,
  message,
  commandItems,
  onMessageChange,
  onPatchChange,
  onSubmitCommand,
  onSubmitPatch,
  onSendMessage,
  onPause,
  onCancelRun,
  onCancelPending,
  onConfirmRepair,
  onRejectRepair,
  onSelectChoice,
  onTogglePlanMode,
  onApprovePlan,
  onRejectPlan,
  onRunPlan,
  onError,
}) {
  return (
    <main className="center">
      <section className="chat-head">
        <PanelTitle icon={ClipboardList} text={ui.sections.conversation || "Conversation"} />
        <div className="session">
          {sessionId ? sessionId.slice(0, 8) : ui.session.noSession} / {ui.statuses[runState.status] || runState.status}
        </div>
      </section>
      <ChatTranscript
        transcript={transcript}
        runState={runState}
        ui={ui}
      />
      {hasPendingInteraction || planDraft ? (
        <section className="interaction-dock">
          {hasPendingInteraction ? (
            <ResumePanel
              ui={ui}
              status={runState.status}
              pendingTask={pendingTask}
              issue={activeIssue}
              risk={activeRisk}
              repair={repair}
              allowedActions={allowedActions}
              resumeMode={resumeMode}
              onModeChange={setResumeMode}
              onConfirm={onConfirmRepair}
              onReject={onRejectRepair}
              onCancel={onCancelPending}
              onChoiceSelect={onSelectChoice}
            />
          ) : null}
          <PlanDraftCard
            plan={planDraft}
            busy={planningBusy}
            onApprove={onApprovePlan}
            onReject={onRejectPlan}
            onRun={onRunPlan}
          />
        </section>
      ) : null}
      <ConversationComposer
        ui={ui}
        llmSettings={llmSettings}
        message={message}
        onMessageChange={onMessageChange}
        commandItems={commandItems}
        runState={runState}
        resumeMode={resumeMode}
        missingSlots={missingSlots}
        pendingTask={pendingTask}
        allowedActions={allowedActions}
        resumePatch={resumePatch}
        resumeFields={resumeFields}
        onPatchChange={onPatchChange}
        onSubmitCommand={onSubmitCommand}
        onSubmitPatch={onSubmitPatch}
        onSendMessage={onSendMessage}
        onPause={onPause}
        onCancelRun={onCancelRun}
        onCancelPending={onCancelPending}
        onTogglePlanMode={onTogglePlanMode}
        planMode={planMode}
        planningBusy={planningBusy}
        onError={onError}
      />
    </main>
  );
}

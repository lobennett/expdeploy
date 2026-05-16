import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: "flanker",
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      }).then(() => {
        document.body.innerHTML += '<p>Flanker done. Loading next...</p>';
        setTimeout(() => location.reload(), 500);
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<h1>Flanker</h1><p>Press any key.</p>" },
  ]);
}

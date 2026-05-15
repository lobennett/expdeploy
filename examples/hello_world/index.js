import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

export default function build() {
  const jsPsych = initJsPsych({
    display_element: "jspsych-target",
    on_finish: () => {
      const payload = {
        exp_id: window.expdeploy.expId,
        subject_id: window.expdeploy.subjectId,
        session_num: window.expdeploy.sessionNum,
        run_num: window.expdeploy.runNum,
        deploy_version: window.expdeploy.deployVersion,
        trials: jsPsych.data.get().values(),
        status: "finished",
      };
      window.expdeploy
        .submit(payload)
        .then((result) => {
          document.body.innerHTML +=
            '<div style="text-align:center;margin-top:2em;">' +
            "<h1>Saved.</h1>" +
            "<p>Path: " +
            (result.path || "(none)") +
            "</p></div>";
        })
        .catch((err) => {
          document.body.innerHTML +=
            '<div style="color:red;text-align:center;margin-top:2em;">' +
            "<h1>Save failed</h1><pre>" +
            String(err) +
            "</pre></div>";
        });
    },
  });

  jsPsych.run([
    {
      type: htmlKeyboardResponse,
      stimulus:
        "<h1>Hello, world!</h1><p>Press any key to finish.</p>",
    },
  ]);
}

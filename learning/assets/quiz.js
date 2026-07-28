/* 재사용 퀴즈 컴포넌트 — retrieval practice 용.
 *
 * 마크업 규약:
 *   <div class="quiz" data-answer="2">
 *     <p class="quiz-q">질문</p>
 *     <ol class="quiz-opts">
 *       <li data-fb="틀린 이유">보기 1</li>
 *       <li data-fb="틀린 이유">보기 2</li>
 *       <li data-fb="맞은 이유">보기 3</li>   <- data-answer 는 1-based
 *     </ol>
 *   </div>
 *
 * 규칙: 모든 보기의 글자 수를 최대한 맞출 것. 길이가 힌트가 되면 회상 연습이 아니다.
 */

(function () {
  const css = `
  .quiz {
    border: 1px solid var(--rule);
    border-radius: 6px;
    padding: 1.1rem 1.2rem;
    margin: 0 0 1.5rem;
    background: color-mix(in srgb, var(--code-bg) 45%, transparent);
  }
  .quiz-label {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 0.66rem; letter-spacing: 0.11em; text-transform: uppercase;
    color: var(--muted); display: block; margin-bottom: 0.55rem;
  }
  .quiz-q { font-weight: 600; margin: 0 0 0.9rem; }
  .quiz-opts { list-style: none; margin: 0; padding: 0; counter-reset: qo; }
  .quiz-opts li {
    position: relative; margin: 0 0 0.45rem; padding: 0.6rem 0.8rem 0.6rem 2.4rem;
    border: 1px solid var(--rule); border-radius: 4px; cursor: pointer;
    background: var(--bg); transition: border-color .12s, background .12s;
    font-size: 0.95rem; counter-increment: qo;
  }
  .quiz-opts li::before {
    content: counter(qo, upper-alpha);
    position: absolute; left: 0.85rem; top: 0.6rem;
    font-family: ui-monospace, Menlo, monospace; font-size: 0.78rem;
    color: var(--muted); font-weight: 600;
  }
  .quiz-opts li:hover:not(.locked) { border-color: var(--accent); }
  .quiz-opts li.correct { border-color: var(--ok); background: color-mix(in srgb, var(--ok) 9%, var(--bg)); }
  .quiz-opts li.wrong   { border-color: var(--accent); background: var(--accent-soft); }
  .quiz-opts li.locked  { cursor: default; }
  .quiz-opts li.dim     { opacity: .5; }
  .quiz-fb {
    display: none; margin-top: 0.55rem; padding-top: 0.55rem;
    border-top: 1px dashed var(--rule); font-size: 0.9rem; color: var(--muted);
  }
  .quiz-fb.show { display: block; }
  .quiz-fb b { color: var(--fg); }
  .quiz-retry {
    margin-top: 0.7rem; font-size: 0.8rem; background: none; border: none;
    color: var(--accent); cursor: pointer; padding: 0;
    border-bottom: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    font-family: inherit;
  }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  document.querySelectorAll(".quiz").forEach(function (quiz) {
    const answer = parseInt(quiz.dataset.answer, 10);
    const opts = Array.from(quiz.querySelectorAll(".quiz-opts li"));

    const label = document.createElement("span");
    label.className = "quiz-label";
    label.textContent = "회상 연습 — 답을 보기 전에 먼저 떠올려 볼 것";
    quiz.insertBefore(label, quiz.firstChild);

    const fb = document.createElement("div");
    fb.className = "quiz-fb";
    quiz.appendChild(fb);

    const retry = document.createElement("button");
    retry.className = "quiz-retry";
    retry.textContent = "다시 풀기";
    retry.style.display = "none";
    quiz.appendChild(retry);

    function reset() {
      opts.forEach(function (o) {
        o.classList.remove("correct", "wrong", "locked", "dim");
      });
      fb.classList.remove("show");
      fb.innerHTML = "";
      retry.style.display = "none";
    }

    opts.forEach(function (opt, i) {
      opt.addEventListener("click", function () {
        if (opt.classList.contains("locked")) return;
        const isRight = i + 1 === answer;

        opts.forEach(function (o, j) {
          o.classList.add("locked");
          if (j + 1 === answer) o.classList.add("correct");
          else if (j === i) o.classList.add("wrong");
          else o.classList.add("dim");
        });

        fb.innerHTML =
          "<b>" + (isRight ? "맞음." : "아님.") + "</b> " + (opt.dataset.fb || "");
        if (!isRight && opts[answer - 1].dataset.fb) {
          fb.innerHTML += "<br><br><b>정답:</b> " + opts[answer - 1].dataset.fb;
        }
        fb.classList.add("show");
        retry.style.display = "inline";
      });
    });

    retry.addEventListener("click", reset);
  });
})();

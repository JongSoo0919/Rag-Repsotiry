from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from vector.query import COLLECTION_NAME, create_retriever, generate_answer


app = FastAPI(title="RAG PoC")


def render_page(question="", answer="", results=None, error=""):
    results = results or []

    escaped_question = escape(question)
    escaped_answer = escape(answer)
    escaped_error = escape(error)

    result_items = []
    for index, result in enumerate(results, start=1):
        section = escape(result.metadata.get("section", "(section 없음)"))
        text = escape(result.page_content)

        result_items.append(
            f"""
            <details>
              <summary>#{index} {section}</summary>
              <pre>{text}</pre>
            </details>
            """
        )

    debug_html = "\n".join(result_items)

    return f"""
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>RAG PoC</title>
        <style>
          body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f6f7f9;
            color: #1f2933;
          }}
          main {{
            width: min(920px, calc(100% - 32px));
            margin: 40px auto;
          }}
          h1 {{
            margin: 0 0 8px;
            font-size: 28px;
          }}
          .meta {{
            margin: 0 0 24px;
            color: #5f6b7a;
            font-size: 14px;
          }}
          form {{
            display: grid;
            gap: 12px;
            margin-bottom: 24px;
          }}
          textarea {{
            width: 100%;
            min-height: 120px;
            box-sizing: border-box;
            padding: 14px;
            border: 1px solid #c8d0d9;
            border-radius: 8px;
            font: inherit;
            resize: vertical;
            background: white;
          }}
          button {{
            width: fit-content;
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            background: #1f6feb;
            color: white;
            font-weight: 700;
            cursor: pointer;
          }}
          section {{
            background: white;
            border: 1px solid #d9e0e8;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 16px;
          }}
          h2 {{
            margin: 0 0 12px;
            font-size: 18px;
          }}
          pre {{
            white-space: pre-wrap;
            word-break: break-word;
            margin: 12px 0 0;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 13px;
            line-height: 1.5;
          }}
          .answer {{
            white-space: pre-wrap;
            line-height: 1.7;
          }}
          .error {{
            color: #b42318;
            white-space: pre-wrap;
          }}
          details {{
            border-top: 1px solid #edf0f3;
            padding: 12px 0;
          }}
          details:first-of-type {{
            border-top: 0;
          }}
          summary {{
            cursor: pointer;
            font-weight: 700;
          }}
          .examples {{
            background: white;
            border: 1px solid #d9e0e8;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 16px;
          }}
          .ex-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 8px 0 14px;
          }}
          .ex {{
            padding: 6px 10px;
            border: 1px solid #c8d0d9;
            border-radius: 6px;
            background: #f6f7f9;
            color: #5f6b7a;
            font-size: 13px;
            cursor: pointer;
          }}
          .ex:hover {{
            background: #eef2f5;
          }}
          .ex-good {{
            margin: 0 0 4px;
            font-size: 14px;
            font-weight: 700;
            color: #1f6feb;
          }}
          .ex-bad {{
            margin: 16px 0 4px;
            font-size: 14px;
            font-weight: 700;
            color: #b42318;
          }}
          .ex-note {{
            margin: 4px 0 0;
            font-size: 12px;
            color: #5f6b7a;
          }}
        </style>
      </head>
      <body>
        <main>
          <h1>RAG PoC</h1>
          <p class="meta">collection: {escape(COLLECTION_NAME)}</p>

          <form method="post" action="/ask">
            <textarea name="question" placeholder="로그 그래프가 안 그려지는 이유가 뭐야?">{escaped_question}</textarea>
            <button type="submit">질문하기</button>
          </form>

          <section class="examples">
            <h2>예시 질문</h2>
            <p class="ex-good">✅ 이 방식이 강한 질문</p>
            <div class="ex-row">
              <button type="button" class="ex" onclick="document.forms[0].question.value=this.textContent">로그 그래프가 안 그려지는 이유가 뭐야?</button>
              <button type="button" class="ex" onclick="document.forms[0].question.value=this.textContent">Alloy 설정에서 무엇이 빠져 있었어?</button>
            </div>
            <p class="ex-bad">⚠️ 이 방식이 약한 질문</p>
            <div class="ex-row">
              <button type="button" class="ex" onclick="document.forms[0].question.value=this.textContent">Deployment를 외부 통신하려면 어떻게 해야 해?</button>
              <button type="button" class="ex" onclick="document.forms[0].question.value=this.textContent">Pod, Deployment, Service는 서로 어떤 관계야?</button>
            </div>
            <p class="ex-note">의미가 비슷한 문서 chunk를 잘 찾지만, 여러 Entity를 관계로 이어 추론하는 질문엔 약합니다.</p>
          </section>

          {"<section><h2>오류</h2><div class='error'>" + escaped_error + "</div></section>" if error else ""}
          {"<section><h2>답변</h2><div class='answer'>" + escaped_answer + "</div></section>" if answer else ""}
          {"<section><h2>검색된 근거</h2>" + debug_html + "</section>" if results else ""}
        </main>
      </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def index():
    return render_page()


@app.post("/ask", response_class=HTMLResponse)
def ask(question: str = Form(...)):
    try:
        retriever = create_retriever()
        results = retriever.invoke(question)
        answer = generate_answer(question, results)
        return render_page(question=question, answer=answer, results=results)
    except Exception as exc:
        return render_page(question=question, error=str(exc))

import { useState } from 'react'

export default function Quiz({ questions }) {
  const [answers, setAnswers] = useState({})
  const [submitted, setSubmitted] = useState(false)

  if (!questions.length) return <p className="muted">Pas de quiz pour ce cours.</p>

  const score = questions.filter((q, i) => answers[i] === q.answer_index).length

  const restart = () => {
    setAnswers({})
    setSubmitted(false)
  }

  return (
    <div>
      {questions.map((q, i) => (
        <div key={i} className="question">
          <p>
            <strong>{i + 1}.</strong> {q.question}
          </p>
          {q.choices.map((choice, j) => {
            let className = 'choice'
            if (submitted && j === q.answer_index) className += ' correct'
            else if (submitted && answers[i] === j) className += ' wrong'
            return (
              <label key={j} className={className}>
                <input
                  type="radio"
                  name={`q${i}`}
                  checked={answers[i] === j}
                  disabled={submitted}
                  onChange={() => setAnswers({ ...answers, [i]: j })}
                />
                {choice}
              </label>
            )
          })}
          {submitted && <p className="explanation">💡 {q.explanation}</p>}
        </div>
      ))}

      {!submitted ? (
        <button className="primary" onClick={() => setSubmitted(true)}>
          Valider mes réponses
        </button>
      ) : (
        <div className="score">
          Score : {score} / {questions.length}
          <button onClick={restart}>Recommencer</button>
        </div>
      )}
    </div>
  )
}

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

const ROOT = dirname(fileURLToPath(import.meta.url))
const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u
const INVALID_DISPLAY_PATTERN = /[\u00b7\u2026\ufffd]|(?:Ã|Â|â€|鈥|榛|楹|锟)/u
const TYPOGRAPHIC_PUNCTUATION_PATTERN = /[\u2010-\u201f]/u

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    const isApplicationSource = ['.js', '.vue'].includes(extname(entry.name))
      && !entry.name.endsWith('.spec.js')
    return isApplicationSource ? [path] : []
  })
}

it('contains only clean ASCII display copy in the Study 1 source tree', () => {
  const offenders = sourceFiles(ROOT).filter(path => (
    CJK_PATTERN.test(readFileSync(path, 'utf8'))
    || INVALID_DISPLAY_PATTERN.test(readFileSync(path, 'utf8'))
    || TYPOGRAPHIC_PUNCTUATION_PATTERN.test(readFileSync(path, 'utf8'))
  ))
  expect(offenders).toEqual([])
})

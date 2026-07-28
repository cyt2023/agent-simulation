import { readdirSync, readFileSync } from 'node:fs'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

const ROOT = dirname(fileURLToPath(import.meta.url))
const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    const isApplicationSource = ['.js', '.vue'].includes(extname(entry.name))
      && !entry.name.endsWith('.spec.js')
    return isApplicationSource ? [path] : []
  })
}

it('contains no CJK application copy in the Study 1 source tree', () => {
  const offenders = sourceFiles(ROOT).filter(path => (
    CJK_PATTERN.test(readFileSync(path, 'utf8'))
  ))
  expect(offenders).toEqual([])
})

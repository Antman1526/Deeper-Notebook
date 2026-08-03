const FILE_URL = /\bfile:\/\/[^\s,;\)\]}>]*/gi
const WINDOWS_ABSOLUTE_PATH = /(?:^|(?<=[\s("'=]))[A-Za-z]:[\\/][^\s,;\)\]}>]*/g
const UNC_ABSOLUTE_PATH = /(?:^|(?<=[\s("'=]))(?:\\\\|\/\/)[^\s,;\)\]}>]*/g
const POSIX_ABSOLUTE_PATH = /(?:^|(?<=[\s("'=]))\/(?!\/)[^\s,;\)\]}>]*/g

export function isAbsoluteFilesystemPath(value: string): boolean {
  return /^(?:\/|\\\\|\/\/|[A-Za-z]:[\\/]|file:\/\/)/i.test(value)
}

/**
 * Redact real filesystem paths while deliberately preserving prose that uses
 * slash punctuation, relative locators, ratios, and HTTPS URLs.
 */
export function redactAbsolutePaths(value: string): string {
  return value
    .replace(FILE_URL, '[path redacted]')
    .replace(WINDOWS_ABSOLUTE_PATH, '[path redacted]')
    .replace(UNC_ABSOLUTE_PATH, '[path redacted]')
    .replace(POSIX_ABSOLUTE_PATH, '[path redacted]')
}

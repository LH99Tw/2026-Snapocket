declare module 'next-svgr' {
  import { NextConfig } from 'next'

  function withSvgr(config: NextConfig): NextConfig

  export default withSvgr
}

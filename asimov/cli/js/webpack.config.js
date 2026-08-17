const path = require('path');
const webpack = require('webpack');

module.exports = {
  mode: 'production',
  entry: './src/index.js',
  output: {
    path: path.resolve(__dirname, '../static'),
    filename: 'mermaid-elk.bundle.js',
  },
  plugins: [
    // Force everything (including Mermaid's dynamic imports) into a single
    // file so reports work from any path without managing multiple chunk URLs.
    new webpack.optimize.LimitChunkCountPlugin({ maxChunks: 1 }),
  ],
};

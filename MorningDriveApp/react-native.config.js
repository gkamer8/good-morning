module.exports = {
  dependencies: {
    'react-native-vector-icons': {
      platforms: {
        ios: null, // We configure fonts manually in Info.plist
      },
    },
  },
  assets: ['./node_modules/react-native-vector-icons/Fonts'],
};

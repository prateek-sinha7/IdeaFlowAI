/**
 * Enterprise-dark design system tokens
 * Color palette for the AI SaaS Platform
 */

export const colors = {
  navy: '#001f3f',
  white: '#FFFFFF',
  grey: '#AAAAAA',
  black: '#000000',
} as const;

export const theme = {
  colors: {
    primary: colors.navy,
    background: colors.black,
    foreground: colors.white,
    muted: colors.grey,
    surface: colors.navy,
    border: colors.grey,
  },
  animation: {
    typingDuration: '1.4s',
    fadeInDuration: '0.3s',
    tabTransitionDuration: '0.2s',
  },
} as const;

export type ThemeColors = typeof theme.colors;
export type ThemeAnimation = typeof theme.animation;

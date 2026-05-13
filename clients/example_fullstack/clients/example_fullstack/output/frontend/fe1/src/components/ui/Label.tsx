import { type LabelHTMLAttributes, type ReactNode, forwardRef } from 'react';

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  children: ReactNode;
}

export const Label = forwardRef<HTMLLabelElement, LabelProps>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <label
        ref={ref}
        className={`block text-sm font-medium text-gray-700 ${className}`}
        {...props}
      >
        {children}
      </label>
    );
  },
);

Label.displayName = 'Label';
